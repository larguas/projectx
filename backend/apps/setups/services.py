"""Couche de services de la feature 05b (app ``setups``).

Règles :
- toute écriture sur les données d'un setup exige l'accès ``setups:write`` au
  profil du sportif rattaché (``core.access`` — jamais de requête directe sur
  les grants, décision n°8) ; le propriétaire du profil y accède toujours ;
- un setup est modifiable librement TANT QU'AUCUNE SÉANCE ne l'utilise. Dès
  qu'il est utilisé (``SensorSetup.is_used``, point d'extension unique pour la
  feature 06), il est figé : PATCH/DELETE/remplacement des canaux sont refusés
  en SERVICE (``SetupsServiceError("setup_frozen")``) ET en MODÈLE
  (``SensorSetup.save()`` appelle ``assert_editable``) — la spec exige cette
  double vérification. Toute modification passe alors par ``new_version`` ;
- ``set_channels`` remplace ATOMIQUEMENT la liste des canaux du setup et
  recalcule le niveau de détail effectif : ``detailed`` si au moins un canal
  porte un champ détaillé (position, distance inter-électrodes, préparation
  cutanée, photo), sinon ``simple`` — c'est l'implémentation de la règle
  « detail_level forcé à simple si les champs détaillés sont vides » ;
- ``DELETE /setups/{id}/`` est refusé si le setup est utilisé (une séance ne
  doit jamais perdre son placement) ou s'il a des versions enfants (la lignée
  ``parent`` est préservée).

Les erreurs lèvent ``SetupsServiceError`` avec un code stable mappé en HTTP
par les vues (``forbidden`` -> 403, ``setup_frozen`` / ``has_newer_version`` /
``has_calibrations`` -> 409). Les cas « non lisible » sont gérés en amont par
les vues (404 — l'existence n'est pas révélée, même convention que les
features 04/05).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.setups.models import SensorSetup


class SetupsServiceError(Exception):
    """Erreur métier des services setups ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_write_access(user, athlete) -> None:
    """Écriture sur les données d'un sportif : scope ``setups:write`` requis."""
    from core import access, scopes

    if not access.can_access_athlete(user, athlete, scopes.SETUPS_WRITE.name):
        raise SetupsServiceError(
            "forbidden",
            "Vous n'avez pas le droit de modifier les setups de ce sportif.",
        )


def _assert_not_used(setup: SensorSetup) -> None:
    """Refuse toute mutation d'un setup figé (utilisé par une séance)."""
    if setup.is_used:
        raise SetupsServiceError(
            "setup_frozen",
            "Ce setup est utilisé par une séance et ne peut plus être modifié ; "
            "créez une nouvelle version (POST /setups/{id}/new-version/).",
        )


def create_setup(user, data: dict) -> SensorSetup:
    """Crée la version 1 d'un setup nommé pour ``data["athlete"]``.

    ``data`` contient les champs validés par ``CreateSetupSerializer``
    (``name``, ``athlete``, ``notes``). Sans canaux au départ, le niveau de
    détail effectif est ``simple`` ; il sera recalculé à la première
    déclaration de canaux (``set_channels``).
    """
    from apps.setups.models import SensorSetup

    athlete = data["athlete"]
    _assert_write_access(user, athlete)
    return SensorSetup.objects.create(
        athlete=athlete,
        name=data["name"],
        version=1,
        is_current=True,
        created_by=user,
        notes=data.get("notes", ""),
    )


def update_setup(user, setup: SensorSetup, data: dict) -> SensorSetup:
    """Met à jour un setup non utilisé (``name``, ``notes``).

    Le rattachement au sportif ne change PAS ici (l'identité d'un setup est
    ``(athlete, name, version)`` : changer l'athlète créerait un autre setup —
    à créer explicitement). Refusé si le setup est utilisé (service ; la
    double vérification modèle passe par ``save()`` -> ``assert_editable``).
    """
    _assert_write_access(user, setup.athlete)
    _assert_not_used(setup)
    for field in ("name", "notes"):
        if field in data:
            setattr(setup, field, data[field])
    setup.save()  # re-vérifie ``assert_editable`` au niveau modèle
    return setup


def delete_setup(user, setup: SensorSetup) -> None:
    """Supprime un setup non utilisé et sans versions enfants.

    Refusé si le setup est utilisé par une séance (``setup_frozen``) ou s'il
    existe des versions qui en descendent (``has_newer_version`` — la lignée
    ``parent`` ne doit pas être cassée). Les canaux sont supprimés en cascade ;
    les calibrations, elles, sont protégées (``PROTECT``) : un canal portant
    une calibration empêche le remplacement/suppression (``has_calibrations``).
    """
    _assert_write_access(user, setup.athlete)
    _assert_not_used(setup)
    if setup.child_versions.exists():
        raise SetupsServiceError(
            "has_newer_version",
            "Ce setup a des versions plus récentes ; supprimez d'abord celles-ci.",
        )
    setup.delete()


def set_channels(user, setup: SensorSetup, entries: list) -> list:
    """Remplace ATOMIQUEMENT les canaux d'un setup non utilisé.

    ``entries`` est la liste COMPLÈTE validée par ``SetChannelsSerializer``
    (doublons ``(device, channel_id)`` déjà refusés). Les canaux existants sont
    supprimés puis les nouveaux créés dans une transaction — un échec
    intermédiaire ne laisse jamais un setup partiel. Un canal portant des
    calibrations empêche le remplacement (les calibrations ne sont jamais
    détruites silencieusement : ``has_calibrations``).

    Le niveau de détail du setup est recalculé ensuite : ``detailed`` si au
    moins un nouveau canal porte un champ détaillé, sinon ``simple``.
    """
    from django.db import transaction

    from apps.setups.models import SetupChannel

    _assert_write_access(user, setup.athlete)
    _assert_not_used(setup)
    if setup.channels.filter(calibrations__isnull=False).exists():
        raise SetupsServiceError(
            "has_calibrations",
            "Un canal de ce setup porte des calibrations ; les canaux ne peuvent "
            "pas être modifiés tant qu'elles existent.",
        )
    with transaction.atomic():
        setup.channels.all().delete()
        channels = [
            SetupChannel(
                setup=setup,
                device=entry.get("device"),
                channel_id=entry["channel_id"],
                muscle=entry["muscle"],
                side=entry.get("side", "na"),
                position_note=entry.get("position_note", ""),
                inter_electrode_distance_mm=entry.get("inter_electrode_distance_mm"),
                skin_prep_done=entry.get("skin_prep_done"),
                photo=entry.get("photo"),
            )
            for entry in entries
        ]
        # Sauvegarde individuelle (pas de bulk_create) : le champ ``photo``
        # n'est écrit dans ``default_storage`` que via ``save()``.
        for channel in channels:
            channel.save()
    _recompute_detail_level(setup, channels)
    return list(setup.channels.all())


def _recompute_detail_level(setup: SensorSetup, channels: list) -> None:
    """Recalcule et persiste le niveau de détail effectif du setup.

    ``detailed`` si au moins un canal porte un champ détaillé, sinon ``simple``
    (règle « forcé à simple si les champs détaillés sont vides »).
    """
    from apps.setups.models import SensorSetup

    level = (
        SensorSetup.DetailLevel.DETAILED
        if any(channel.has_detailed_fields for channel in channels)
        else SensorSetup.DetailLevel.SIMPLE
    )
    if setup.detail_level != level:
        setup.detail_level = level
        setup.save()
