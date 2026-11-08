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
  ``parent`` est préservée) ;
- ``compare_setups(a, b)`` calcule le niveau de comparabilité de deux setups
  (``identical`` / ``equivalent`` / ``approximate`` / ``different`` /
  ``unknown``) et des raisons stables et lisibles — la brique de crédibilité
  des analyses ; l'IA les réutilisera comme caveats (feature 12). C'est une
  lecture : le contrôle d'accès (``setups:read`` sur chaque setup) est fait en
  vue, pas ici.

Les erreurs lèvent ``SetupsServiceError`` avec un code stable mappé en HTTP
par les vues : ``forbidden`` -> 403 ; ``setup_frozen`` / ``has_newer_version``
/ ``has_calibrations`` / ``name_taken`` / ``already_invalidated`` -> 409. Les
cas « non lisible » sont gérés en amont par les vues (404 — l'existence n'est
pas révélée, même convention que les features 04/05).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from apps.setups.models import Calibration, SensorSetup


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

    Un nom déjà porté par une version existante du même sportif est refusé
    (``name_taken``, 409) : l'identité d'un setup est ``(athlete, name,
    version)``, et créer un doublon v1 casserait la lignée — pour modifier un
    placement existant on passe par ``new_version``.
    """
    from apps.setups.models import SensorSetup

    athlete = data["athlete"]
    _assert_write_access(user, athlete)
    if SensorSetup.objects.filter(athlete=athlete, name=data["name"]).exists():
        raise SetupsServiceError(
            "name_taken",
            "Ce sportif a déjà un setup de ce nom ; modifiez-le ou créez une "
            "nouvelle version (POST /setups/{id}/new-version/).",
        )
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

    Refusé si le setup est utilisé par une séance (``setup_frozen``), s'il
    porte des calibrations (``has_calibrations`` — les calibrations ne sont
    jamais détruites silencieusement, même en cascade) ou s'il existe des
    versions qui en descendent (``has_newer_version`` — la lignée ``parent``
    ne doit pas être cassée). Les canaux sans calibration sont supprimés en
    cascade.
    """
    _assert_write_access(user, setup.athlete)
    _assert_not_used(setup)
    if setup.calibrations.exists() or setup.channels.filter(calibrations__isnull=False).exists():
        raise SetupsServiceError(
            "has_calibrations",
            "Ce setup porte des calibrations ; il ne peut pas être supprimé.",
        )
    if setup.child_versions.exists():
        raise SetupsServiceError(
            "has_newer_version",
            "Ce setup a des versions plus récentes ; supprimez d'abord celles-ci.",
        )
    setup.delete()


def new_version(user, setup: SensorSetup, data: dict) -> SensorSetup:
    """Crée la version n+1 d'un setup (``POST /setups/{id}/new-version/``).

    La nouvelle version est une COPIE COMPLÈTE de ``setup`` (nom, notes, niveau
    de détail, canaux avec photos), ``parent = setup``, ``is_current=True`` —
    et la version source passe en ``is_current=False``. N'étant pas encore
    utilisée, la copie reste librement modifiable (PATCH / remplacement des
    canaux) jusqu'à sa première utilisation par une séance.

    ``data["placement_unchanged"]`` (booléen, défaut ``False``) : True quand
    l'utilisateur affirme que seul un détail NON PHYSIQUE change (nom, notes).
    Dans ce cas les calibrations de la version précédente sont RATTACHÉES à la
    nouvelle version (chaque calibration suit son canal copié) — une MVC reste
    valable pour le même placement. Sinon elles restent liées à l'ancienne
    version et ne s'appliquent pas à la nouvelle (une MVC n'a de sens que pour
    un placement donné). Le fait est mémorisé sur la nouvelle version
    (``placement_inherited_from_parent``) : c'est ce qui permet au service de
    comparaison de qualifier une lignée ``identical``.

    Le basculement ``is_current`` passe par une mise à jour en base ciblée —
    jamais de ``save()`` sur la version source, potentiellement figée.
    """
    from django.db import transaction
    from django.db.models import Max

    from apps.setups.models import Calibration, SensorSetup, SetupChannel

    _assert_write_access(user, setup.athlete)
    placement_unchanged = bool(data.get("placement_unchanged", False))
    with transaction.atomic():
        next_version = (
            SensorSetup.objects.filter(athlete=setup.athlete, name=setup.name).aggregate(
                max_version=Max("version")
            )["max_version"]
            or 0
        ) + 1
        new_setup = SensorSetup.objects.create(
            athlete=setup.athlete,
            name=setup.name,
            version=next_version,
            parent=setup,
            placement_inherited_from_parent=placement_unchanged,
            detail_level=setup.detail_level,
            is_current=True,
            created_by=user,
            notes=setup.notes,
        )
        channel_map: dict = {}
        for old_channel in setup.channels.all():
            new_channel = SetupChannel(
                setup=new_setup,
                device_id=old_channel.device_id,
                channel_id=old_channel.channel_id,
                muscle_id=old_channel.muscle_id,
                side=old_channel.side,
                position_note=old_channel.position_note,
                inter_electrode_distance_mm=old_channel.inter_electrode_distance_mm,
                skin_prep_done=old_channel.skin_prep_done,
                photo=old_channel.photo,  # partage le même fichier stocké
            )
            new_channel.save()
            channel_map[old_channel.pk] = new_channel
        SensorSetup.objects.filter(pk=setup.pk).update(is_current=False)
        if placement_unchanged:
            for calibration in Calibration.objects.filter(setup=setup):
                calibration.setup = new_setup
                calibration.setup_channel = channel_map[calibration.setup_channel_id]
                calibration.save(update_fields=("setup", "setup_channel", "updated_at"))
    return new_setup


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


def applicable_calibrations(setup: SensorSetup):
    """Calibrations APPLICABLES au ``setup`` (version précise) donné.

    Implémente la règle d'applicabilité du doc 05b : une calibration est
    applicable si — et seulement si — elle est non invalidée, non expirée ET
    rattachée au setup de la séance. La troisième condition est portée par le
    filtre sur ``setup`` : une calibration d'une autre version (ou d'un autre
    nom de setup) ne s'applique jamais ici — une MVC n'a de sens que pour un
    placement donné, et ``new_version`` sans ``placement_unchanged`` ne la
    déplace pas.

    Retourne un ``QuerySet[Calibration]`` (filtrable ensuite par type/canal en
    vue) ; vide si aucune calibration n'est applicable.
    """
    from django.db.models import Q

    from apps.setups.models import Calibration

    return (
        Calibration.objects.filter(setup=setup, invalidated_at__isnull=True)
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=timezone.now()))
        .select_related("setup_channel")
    )


def invalidate_calibration(user, calibration: Calibration, reason: str) -> Calibration:
    """Invalide une calibration avec un motif (``POST /calibrations/{id}/invalidate/``).

    L'invalidation est IRRÉVERSIBLE côté API (pas de réactivation : on crée une
    nouvelle calibration) et se marque par ``invalidated_at`` +
    ``invalidation_reason`` — la calibration n'est plus jamais renvoyée par
    ``applicable_calibrations``. Le traçage (événement ``calibration.invalidated``)
    est fait par la vue, comme pour les autres événements d'audit de l'app.

    Refusé si la calibration est déjà invalidée (``already_invalidated``, 409).
    """
    _assert_write_access(user, calibration.athlete)
    if calibration.invalidated_at is not None:
        raise SetupsServiceError(
            "already_invalidated",
            "Cette calibration est déjà invalidée.",
        )
    calibration.invalidated_at = timezone.now()
    calibration.invalidation_reason = reason
    calibration.save(update_fields=("invalidated_at", "invalidation_reason", "updated_at"))
    return calibration


def compare_setups(a: SensorSetup | None, b: SensorSetup | None) -> dict:
    """Niveau de comparabilité entre deux setups (doc 05b, spec §8.5).

    Args:
        a: premier setup (ou ``None`` s'il est introuvable / non visible —
          la vue ne révèle pas l'existence).
        b: second setup (idem).

    Returns:
        ``{"level", "reasons"}`` avec un niveau parmi :
        - ``identical`` : même version, ou même lignée où aucune version
          intermédiaire n'a modifié le placement (``placement_unchanged``) ;
        - ``equivalent`` : deux setups détaillés, même correspondance
          muscle/côté par canal, mêmes distances inter-électrodes, même modèle
          d'appareil ;
        - ``approximate`` : même correspondance muscle/côté mais au moins un
          setup en mode simple, ou (détaillés) distances / modèles d'appareil
          non alignés ;
        - ``different`` : correspondance muscle/côté différente ;
        - ``unknown`` : l'un des deux setups est absent.

    Les ``reasons`` sont stables et lisibles : l'IA les réutilisera comme
    caveats (feature 12). Interprétations documentées (trous de spec) :
    - deux setups détaillés de la même lignée dont le placement a changé entre
      eux sont évalués sur leurs canaux (la condition « lignées différentes »
      d'``equivalent`` est une conséquence, pas un prérequis) ;
    - deux setups détaillés alignés muscle/côté mais avec distances ou modèles
      d'appareil différents sont ``approximate`` : la correspondance sémantique
      reste bonne.
    """
    from apps.setups.models import SensorSetup

    if a is None or b is None:
        return {
            "level": "unknown",
            "reasons": ["Un des deux setups est absent."],
        }
    if a.pk == b.pk:
        return {"level": "identical", "reasons": ["Même setup (même version)."]}

    same_lineage, placement_preserved = _lineage_relation(a, b)
    if same_lineage and placement_preserved:
        return {
            "level": "identical",
            "reasons": [
                "Même lignée de placement : aucune version intermédiaire n'a modifié le placement."
            ],
        }

    channels_a = list(a.channels.all())
    channels_b = list(b.channels.all())
    pairs_a = sorted((c.muscle.code, c.side) for c in channels_a)
    pairs_b = sorted((c.muscle.code, c.side) for c in channels_b)
    if pairs_a != pairs_b:
        from collections import Counter

        diff = (Counter(pairs_a) - Counter(pairs_b)) + (Counter(pairs_b) - Counter(pairs_a))
        labels = ", ".join(f"{muscle} ({side})" for muscle, side in sorted(diff.elements()))
        return {
            "level": "different",
            "reasons": [f"Correspondance muscle/côté différente : {labels}."],
        }

    if (
        a.detail_level != SensorSetup.DetailLevel.DETAILED
        or b.detail_level != SensorSetup.DetailLevel.DETAILED
    ):
        return {
            "level": "approximate",
            "reasons": [
                "Au moins un des setups est en mode simple : position et distances non déclarées."
            ],
        }

    distances_ok, distances_reason = _distances_match(channels_a, channels_b)
    models_ok, models_reason = _device_models_match(channels_a, channels_b)
    if distances_ok and models_ok:
        return {
            "level": "equivalent",
            "reasons": [
                "Setups détaillés alignés : même correspondance muscle/côté, "
                "mêmes distances inter-électrodes, même modèle d'appareil."
            ],
        }
    reasons = [r for r in (distances_reason, models_reason) if r]
    return {"level": "approximate", "reasons": reasons}


def _lineage_relation(a: SensorSetup, b: SensorSetup):
    """Relation de lignée entre deux versions d'un même nom de setup.

    Retourne ``(même_lignée, placement_préservé)`` : ``même_lignée`` si l'une
    est un ancêtre de l'autre (chaîne ``parent``), ``placement_préservé`` si
    toutes les transitions entre elles ont été créées avec
    ``placement_unchanged=True`` (marque ``placement_inherited_from_parent``).
    Deux branches distinctes d'une même famille ne forment pas une lignée
    directe : la comparaison retombe sur les canaux.
    """
    from apps.setups.models import SensorSetup

    if a.athlete_id != b.athlete_id or a.name != b.name:
        return False, False
    versions = {v.pk: v for v in SensorSetup.objects.filter(athlete_id=a.athlete_id, name=a.name)}

    def ancestor_of(x_pk, y):
        cur = versions.get(y.parent_id) if y.parent_id else None
        while cur is not None:
            if cur.pk == x_pk:
                return True
            cur = versions.get(cur.parent_id) if cur.parent_id else None
        return False

    if ancestor_of(a.pk, b):
        shallower, deeper = a, b
    elif ancestor_of(b.pk, a):
        shallower, deeper = b, a
    else:
        return True, False  # même famille (même nom), branches distinctes

    cur = deeper
    while cur.pk != shallower.pk:
        if not cur.placement_inherited_from_parent:
            return True, False
        cur = versions.get(cur.parent_id)
        if cur is None:
            return True, False  # incohérent (parent PROTECT) : non garantissable
    return True, True


def _distances_match(channels_a: list, channels_b: list):
    """Mêmes distances inter-électrodes par groupe (muscle, côté)."""

    def groups(channels):
        out = {}
        for channel in channels:
            key = (channel.muscle.code, channel.side)
            out.setdefault(key, []).append(channel.inter_electrode_distance_mm)
        return {k: sorted(v, key=lambda v: (v is None, v)) for k, v in out.items()}

    if groups(channels_a) == groups(channels_b):
        return True, None
    return False, "Distances inter-électrodes différentes ou non déclarées sur au moins un canal."


def _device_models_match(channels_a: list, channels_b: list):
    """Même modèle d'appareil sur tous les canaux des deux setups."""

    def declared_models(channels):
        return sorted(
            {
                (channel.device.device_model.manufacturer, channel.device.device_model.name)
                for channel in channels
                if channel.device_id is not None
            }
        )

    all_declared = all(
        channel.device_id is not None for channel in list(channels_a) + list(channels_b)
    )
    if not all_declared:
        return False, "Modèle d'appareil non déclaré sur au moins un canal."
    models_a, models_b = declared_models(channels_a), declared_models(channels_b)
    if models_a == models_b:
        return True, None

    def label(models):
        return ", ".join(f"{manufacturer} {name}" for manufacturer, name in models)

    return False, f"Modèles d'appareil différents : {label(models_a)} vs {label(models_b)}."
