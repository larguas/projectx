"""Couche de services de la feature 06 (app ``sessions``).

Règles :
- le statut suit UNIQUEMENT la machine à états du modèle (``created →
  recording → completed | cancelled | failed``) ; chaque transition passe par
  un service dédié avec verrouillage ``select_for_update``, jamais par un
  serializer — toute autre transition est refusée (``invalid_transition``,
  409) ;
- la création vérifie le droit d'écriture du créateur sur le sportif
  (``core.access``, scope ``sessions:write``), l'accessibilité de chaque
  appareil utilisé et la compatibilité des canaux avec les capacités du modèle
  d'appareil (``DeviceModel.capabilities``) ;
- si un ``setup`` est fourni, ses ``SetupChannel`` sont copiés en
  ``SessionChannel`` (muscle/côté figés) et le setup devient immuable : le
  marqueur ``used_at`` est posé par une mise à jour EN BASE ciblée (jamais de
  ``save()`` — point d'extension du doc 05b, fermé ici) ; sans setup, la
  séance est acceptée avec ``setup_declared = False`` et un avertissement
  ``setup_not_declared`` (renvoyé par la vue dans la réponse ET le détail) ;
- une séance ``calibration`` exige un ``setup`` ET un ``calibration_type``
  (validation croisée du sérialiseur de création — erreur de forme, 400) ;
- les annotations sont autorisées pendant ``recording`` et après ``completed``,
  jamais sur ``created`` / ``cancelled`` / ``failed`` (``annotation_blocked``,
  409) ;
- canaux et appareils d'une séance ne sont modifiables QUE pendant ``created``
  (``locked``, 409) : une fois l'enregistrement démarré, le jeu de canaux est
  figé car les données ingérées (feature 07) s'y rattachent.

Les erreurs lèvent ``SessionsServiceError`` avec un code stable mappé en HTTP
par les vues (``forbidden`` -> 403 ; ``not_found`` -> 404 ;
``invalid_transition`` / ``capability_exceeded`` / ``annotation_blocked`` /
``setup_incomplete`` / ``locked`` / ``device_not_in_session`` /
``channels_reference_device`` -> 409).

Hook : ``on_session_completed(session)`` est appelé APRÈS le commit de la
transition vers ``completed`` — vide en feature 06, branché en features 07 et
09 (il reçoit la séance dont le champ ``session_type`` permet à la feature 09
de créer la calibration correspondante via ``Calibration.source_session``).
Un échec du hook ne doit pas casser l'état de la séance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover — annotations uniquement (imports locaux au runtime)
    from apps.sessions.models import Session, SessionAnnotation

logger = structlog.get_logger(__name__)


class SessionsServiceError(Exception):
    """Erreur métier des services sessions ; ``code`` est le code stable de l'API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _assert_write_access(user, athlete) -> None:
    """Écriture sur les données d'un sportif : scope ``sessions:write`` requis.

    Le propriétaire du profil et un superutilisateur passent toujours ; un
    coach / membre d'équipe exige un grant actif portant le scope (vérifié par
    ``core.access.can_access_athlete`` — point de contrôle unique).
    """
    from core import access, scopes

    if not access.can_access_athlete(user, athlete, scopes.SESSIONS_WRITE.name):
        raise SessionsServiceError(
            "forbidden",
            "Vous n'avez pas le droit de modifier les séances de ce sportif.",
        )


def _assert_annotation_allowed(session) -> None:
    """Annotations autorisées pendant ``recording`` et après ``completed``.

    Jamais sur une séance ``created`` (pas encore d'acquisition, donc pas
    d'horloge de référence pour ``offset_ms``), ``cancelled`` ni ``failed``
    (données non exploitables) — cf. doc 06 « Règles métier ».
    """
    from apps.sessions.models import Session

    if session.status not in (Session.Status.RECORDING, Session.Status.COMPLETED):
        raise SessionsServiceError(
            "annotation_blocked",
            "Les annotations ne sont autorisées que pendant l'enregistrement "
            "ou après la fin de la séance.",
        )


def _check_device_capabilities(device, channel_entries: list[dict]) -> None:
    """Les canaux déclarés pour ``device`` respectent-ils les capacités du modèle ?

    Deux règles issues de ``DeviceModel.capabilities`` (JSON) :

    - ``emg_channels_max`` : nombre maximal de canaux EMG par appareil
      (types ``emg_raw`` / ``emg_envelope``) ;
    - ``imu`` : si ``False``, aucun canal IMU (``imu_*``) n'est autorisé.

    Une capacité absente du JSON n'est pas contrôlée (modèle non documenté —
    on ne bloque jamais l'acquisition sur une donnée manquante).
    """
    from apps.sessions.models import SessionChannel

    capabilities = device.device_model.capabilities or {}
    emg_types = (SessionChannel.DataType.EMG_RAW, SessionChannel.DataType.EMG_ENVELOPE)
    emg_count = sum(1 for entry in channel_entries if entry["data_type"] in emg_types)
    max_emg = capabilities.get("emg_channels_max")
    if max_emg is not None and emg_count > int(max_emg):
        raise SessionsServiceError(
            "capability_exceeded",
            f"Le capteur {device.id} ne supporte que {max_emg} canaux EMG ; "
            f"{emg_count} sont déclarés pour cette séance.",
        )
    if capabilities.get("imu") is False and any(
        str(entry["data_type"]).startswith("imu_") for entry in channel_entries
    ):
        raise SessionsServiceError(
            "capability_exceeded",
            f"Le capteur {device.id} ne dispose pas de capteurs IMU ; des canaux "
            "IMU sont déclarés pour cette séance.",
        )


def _assert_device_accessible(user, device) -> None:
    """L'appareil doit être ACCESSIBLE au demandeur (propriétaire ou grant).

    « Accessible » = même règle que la lecture d'un capteur en feature 04
    (``apps.devices.selectors.can_read_device``) : un coach qui crée une séance
    pour son sportif doit pouvoir lire les capteurs de ce sportif.
    """
    from apps.devices.selectors import can_read_device

    if not can_read_device(user, device):
        raise SessionsServiceError(
            "forbidden",
            f"Le capteur {device.id} n'est pas accessible pour cette séance.",
        )


def _group_by_device(channel_entries: list[dict]) -> dict:
    """Regroupe des entrées de canaux par appareil (ordre d'apparition conservé)."""
    grouped: dict = {}
    for entry in channel_entries:
        grouped.setdefault(entry["device"].pk, []).append(entry)
    return grouped


def _frozen_calibrations_by_channel(setup) -> dict:
    """Copies FIGÉES des calibrations applicables du setup, par canal de setup.

    Utilise ``applicable_calibrations`` (feature 05b) : non invalidées, non
    expirées ET rattachées à cette version précise du setup. La copie gelée ne
    porte que les informations utiles au traitement des signaux (type, valeurs,
    version d'algorithme) — jamais l'identifiant de la calibration, qui reste
    une entité vivante gérée par la feature 05b/09.
    """
    from apps.setups.services import applicable_calibrations

    frozen: dict = {}
    for calibration in applicable_calibrations(setup):
        frozen.setdefault(calibration.setup_channel_id, []).append(
            {
                "type": calibration.type,
                "values": calibration.values,
                "algorithm_version": calibration.algorithm_version,
            }
        )
    return frozen


def create_session(user, data: dict) -> tuple[Session, list[str]]:
    """Crée une séance au statut ``created`` ; retourne ``(session, warnings)``.

    ``data`` contient les champs validés par ``SessionCreateSerializer`` :
    ``athlete``, ``session_type``, ``setup`` (nullable), ``calibration_type``
    (nullable), ``exercise`` / ``workout`` (nullable), ``source``,
    ``protocol_version``, ``notes``, ``acquisition_config`` et ``channels``
    (déclaration manuelle — refusée en validation si un setup est fourni).

    Avec un setup : les ``SetupChannel`` sont copiés en ``SessionChannel``
    (muscle/côté figés, ``setup_channel`` garde la référence d'origine) et les
    calibrations applicables du setup sont gelées dans le champ ``calibration``
    de chaque canal. Le setup devient IMMUEABLE : le marqueur ``used_at`` est
    posé par une mise à jour en base ciblée (jamais de ``save()`` — un setup
    figé refuse d'être sauvegardé au niveau modèle, cf. doc 05b).

    Sans setup : ``setup_declared = False`` et l'avertissement
    ``setup_not_declared`` est retourné à la vue (réponse ET détail de la
    séance). Les appareils des canaux deviennent des ``SessionDevice`` : le
    premier appareil distinct (ordre de déclaration) prend le rôle ``primary``,
    les autres ``secondary``.
    """
    from apps.sessions.models import Session, SessionChannel, SessionDevice
    from apps.setups.models import SensorSetup

    athlete = data["athlete"]
    _assert_write_access(user, athlete)

    setup: SensorSetup | None = data.get("setup")
    warnings: list[str] = [] if setup is not None else ["setup_not_declared"]

    # --- Canaux : copiés depuis le setup, ou déclarés à la main (sans setup).
    if setup is not None:
        frozen_by_channel = _frozen_calibrations_by_channel(setup)
        channel_entries = []
        for setup_channel in setup.channels.all():
            if setup_channel.device_id is None:
                raise SessionsServiceError(
                    "setup_incomplete",
                    "Ce setup contient des canaux sans capteur ; ils ne peuvent "
                    "pas être copiés dans une séance. Complétez le placement "
                    "(nouvelle version du setup) avant de créer la séance.",
                )
            channel_entries.append(
                {
                    "device": setup_channel.device,
                    "channel_id": setup_channel.channel_id,
                    "muscle": setup_channel.muscle,
                    "side": setup_channel.side,
                    "data_type": SessionChannel.DataType.EMG_RAW,
                    "units": "",
                    "setup_channel": setup_channel,
                    "calibration": frozen_by_channel.get(setup_channel.pk),
                }
            )
    else:
        channel_entries = [
            {**entry, "setup_channel": None, "calibration": None}
            for entry in data.get("channels", [])
        ]

    # --- Appareils : accessibilité du demandeur + capacités du modèle.
    # (les clés du dictionnaire sont des pks — l'appareil est repris de la
    # première entrée du groupe).
    devices_grouped = _group_by_device(channel_entries)
    for entries in devices_grouped.values():
        device = entries[0]["device"]
        _assert_device_accessible(user, device)
        _check_device_capabilities(device, entries)

    with transaction.atomic():
        session = Session.objects.create(
            athlete=athlete,
            created_by=user,
            session_type=data["session_type"],
            setup=setup,
            setup_declared=setup is not None,
            exercise=data.get("exercise"),
            workout=data.get("workout"),
            source=data.get("source", Session.Source.MOBILE),
            protocol_version=data.get("protocol_version", 1),
            notes=data.get("notes", ""),
            acquisition_config=data.get("acquisition_config") or {},
            calibration_type=data.get("calibration_type"),
        )
        if channel_entries:
            SessionChannel.objects.bulk_create(
                SessionChannel(session=session, **entry) for entry in channel_entries
            )
            # Premier appareil distinct (ordre de déclaration) = primaire :
            # son horloge fait référence pour les ``offset_ms`` des annotations.
            session_devices = [entries[0]["device"] for entries in devices_grouped.values()]
            roles = iter(
                [SessionDevice.Role.PRIMARY]
                + [SessionDevice.Role.SECONDARY] * (len(session_devices) - 1)
            )
            SessionDevice.objects.bulk_create(
                SessionDevice(session=session, device=device, role=next(roles))
                for device in session_devices
            )
        if setup is not None:
            # Point d'extension du doc 05b, fermé ici : mise à jour EN BASE
            # ciblée (jamais de ``save()`` — qui déclencherait
            # ``assert_editable`` sur un setup déjà figé). Ne pose le marqueur
            # qu'à la PREMIÈRE utilisation ; une séance peut réutiliser un
            # setup déjà utilisé.
            SensorSetup.objects.filter(pk=setup.pk, used_at__isnull=True).update(
                used_at=timezone.now()
            )

    return session, warnings


def _assert_editable_session(locked) -> None:
    """Canaux et appareils ne sont modifiables QUE pendant ``created``.

    Une fois l'enregistrement démarré, le jeu de canaux est figé : les données
    ingérées (feature 07) s'y rattachent par ``(session, device, channel_id)``.
    """
    from apps.sessions.models import Session

    if locked.status != Session.Status.CREATED:
        raise SessionsServiceError(
            "locked",
            "Canaux et appareils ne sont modifiables que tant que la séance est "
            "au statut « créée ».",
        )


def replace_channels(user, session_pk: str, channel_entries: list[dict]) -> Session:
    """Remplacement INTÉGRAL des canaux (``PUT /sessions/{id}/channels/``).

    Uniquement pendant ``created`` (``locked``, 409). Les mêmes contrôles que
    la création s'appliquent : accessibilité de chaque appareil au demandeur,
    compatibilité avec les capacités du modèle d'appareil. Les lignes
    ``SessionDevice`` sont re-dérivées des nouveaux canaux (premier appareil
    distinct en ordre de déclaration = primaire) — l'invariant « ensemble des
    appareils == ensemble des appareils référencés par les canaux » est ainsi
    conservé par construction.

    ``channel_entries`` : entrées validées par ``SessionChannelInputSerializer``
    (``device``, ``channel_id``, ``muscle``, ``side``, ``data_type``, ``units``).
    """
    from apps.sessions.models import Session, SessionChannel, SessionDevice

    with transaction.atomic():
        locked = Session.objects.select_for_update().filter(pk=session_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Séance introuvable.")
        _assert_write_access(user, locked.athlete)
        _assert_editable_session(locked)

        for entry in channel_entries:
            _assert_device_accessible(user, entry["device"])
        devices_grouped = _group_by_device(channel_entries)
        for entries in devices_grouped.values():
            _check_device_capabilities(entries[0]["device"], entries)

        SessionChannel.objects.filter(session=locked).delete()
        if channel_entries:
            SessionChannel.objects.bulk_create(
                SessionChannel(session=locked, setup_channel=None, calibration=None, **entry)
                for entry in channel_entries
            )
        SessionDevice.objects.filter(session=locked).delete()
        if devices_grouped:
            roles = iter(
                [SessionDevice.Role.PRIMARY]
                + [SessionDevice.Role.SECONDARY] * (len(devices_grouped) - 1)
            )
            SessionDevice.objects.bulk_create(
                SessionDevice(session=locked, device=entries[0]["device"], role=next(roles))
                for entries in devices_grouped.values()
            )
    return locked


def replace_devices(user, session_pk: str, device_entries: list[dict]) -> Session:
    """Remplacement INTÉGRAL des rôles d'appareils (``PUT /sessions/{id}/devices/``).

    Uniquement pendant ``created`` (``locked``, 409). L'ensemble des appareils
    fournis doit être EXACTEMENT celui référencé par les canaux de la séance —
    on ne gère ici que les RÔLES (primaire / secondaires), jamais l'ajout ou le
    retrait d'un appareil, qui passe par ``replace_channels``. Au plus un
    appareil primaire (son horloge fait référence pour les ``offset_ms``).

    ``device_entries`` : ``{"device": Device, "role": "primary"|"secondary"}``.
    """
    from apps.sessions.models import Session, SessionDevice

    with transaction.atomic():
        locked = Session.objects.select_for_update().filter(pk=session_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Séance introuvable.")
        _assert_write_access(user, locked.athlete)
        _assert_editable_session(locked)

        provided = {entry["device"].pk: entry["role"] for entry in device_entries}
        referenced = set(locked.channels.values_list("device_id", flat=True))
        missing = referenced - provided.keys()
        if missing:
            raise SessionsServiceError(
                "channels_reference_device",
                "Des canaux de la séance référencent des appareils absents de la liste fournie.",
            )
        extra = provided.keys() - referenced
        if extra:
            raise SessionsServiceError(
                "device_not_in_session",
                "La liste fournie contient des appareils qui ne sont pas utilisés "
                "par les canaux de la séance.",
            )
        primaries = [pk for pk, role in provided.items() if role == SessionDevice.Role.PRIMARY]
        if len(primaries) > 1:
            raise SessionsServiceError(
                "device_not_in_session",
                "Au plus un appareil primaire par séance.",
            )
        for entry in device_entries:
            _assert_device_accessible(user, entry["device"])

        SessionDevice.objects.filter(session=locked).delete()
        if device_entries:
            SessionDevice.objects.bulk_create(
                SessionDevice(session=locked, **entry) for entry in device_entries
            )
    return locked


def update_session(user, session_pk: str, data: dict) -> Session:
    """Met à jour ``notes`` / ``acquisition_config`` d'une séance.

    Uniquement pendant ``created`` (``locked``, 409) : une fois l'enregistrement
    démarré, la configuration d'acquisition est figée car les données ingérées
    (feature 07) s'y rattachent. Le statut ne passe JAMAIS par ici — voir les
    transitions dédiées (``start_session`` / ``complete_session`` /
    ``cancel_session``).
    """
    from apps.sessions.models import Session

    with transaction.atomic():
        locked = Session.objects.select_for_update().filter(pk=session_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Séance introuvable.")
        _assert_write_access(user, locked.athlete)
        _assert_editable_session(locked)
        for field, value in data.items():
            setattr(locked, field, value)
        locked.save()
    return locked


def _transition(user, session_pk: str, target_status: str, **extra_fields) -> Session:
    """Transition verrouillée de la machine à états vers ``target_status``.

    La ligne est relue sous ``select_for_update`` : deux transitions
    concurrentes (ex. ``complete`` et ``cancel`` simultanés) sont sérialisées —
    seule la première passe, la seconde voit l'état déjà changé et reçoit
    ``invalid_transition`` (409). Le contrôle d'accès en écriture est refait ICI
    (après le verrou) : c'est le filet de sécurité ; la vue a déjà filtré la
    lecture (404 si la séance n'est pas visible par l'utilisateur).
    """
    from apps.sessions.models import Session

    with transaction.atomic():
        locked = Session.objects.select_for_update().filter(pk=session_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Séance introuvable.")
        _assert_write_access(user, locked.athlete)
        if not locked.can_transition_to(target_status):
            raise SessionsServiceError(
                "invalid_transition",
                f"Transition refusée : « {locked.status} » → « {target_status} » "
                "n'est pas autorisée par la machine à états.",
            )
        locked.status = target_status
        for field, value in extra_fields.items():
            setattr(locked, field, value)
        locked.save()
    return locked


def start_session(user, session_pk: str) -> Session:
    """``created → recording`` ; pose ``started_at``."""
    from apps.sessions.models import Session

    return _transition(user, session_pk, Session.Status.RECORDING, started_at=timezone.now())


def complete_session(user, session_pk: str) -> Session:
    """``recording → completed`` ; pose ``ended_at`` puis appelle le hook.

    Le hook ``on_session_completed`` est appelé APRÈS le commit de la
    transition : un échec du hook ne doit jamais casser l'état de la séance
    (décision documentée — loggé pour observabilité, jamais propagé).
    """
    from apps.sessions.models import Session

    session = _transition(user, session_pk, Session.Status.COMPLETED, ended_at=timezone.now())
    try:
        on_session_completed(session)
    except Exception:  # noqa: BLE001 — le hook est un point d'extension, jamais bloquant
        logger.exception("session.completed_hook_failed", session_id=session.pk)
    return session


def cancel_session(user, session_pk: str) -> Session:
    """``created | recording → cancelled`` ; pose ``ended_at``."""
    from apps.sessions.models import Session

    return _transition(user, session_pk, Session.Status.CANCELLED, ended_at=timezone.now())


def fail_session(user, session_pk: str) -> Session:
    """``recording → failed`` ; pose ``ended_at``.

    Pas d'endpoint public en feature 06 : la transition est déclenchée par la
    feature 07 (échec de réception des blocs de données).
    """
    from apps.sessions.models import Session

    return _transition(user, session_pk, Session.Status.FAILED, ended_at=timezone.now())


def on_session_completed(session) -> None:
    """Hook appelé après ``complete_session`` — vide en feature 06.

    Branché en features 07 et 09 : pour une séance ``session_type =
    calibration``, la feature 09 créera la calibration correspondante via
    ``Calibration.source_session`` (le champ ``session_type`` de la séance est
    l'information transmise au hook). Un échec du hook ne doit pas casser
    l'état de la séance : le point d'appel logge et continue.
    """


def create_annotation(user, session_pk: str, data: dict) -> SessionAnnotation:
    """Crée une annotation sur la séance.

    ``data`` contient les champs validés par ``AnnotationSerializer`` (``kind``,
    ``offset_ms``, ``text``, ``metadata``). La séance doit être en
    ``recording`` ou ``completed`` (jamais ``created`` / ``cancelled`` /
    ``failed`` — ``annotation_blocked``, 409).
    """
    from apps.sessions.models import Session, SessionAnnotation

    with transaction.atomic():
        locked = Session.objects.select_for_update().filter(pk=session_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Séance introuvable.")
        _assert_write_access(user, locked.athlete)
        _assert_annotation_allowed(locked)
        return SessionAnnotation.objects.create(session=locked, author=user, **data)


def update_annotation(user, annotation_pk: str, data: dict) -> SessionAnnotation:
    """Met à jour une annotation (mêmes règles de statut que la création).

    ``session`` et ``author`` ne sont jamais modifiables par l'API.
    """
    from apps.sessions.models import SessionAnnotation

    with transaction.atomic():
        locked = SessionAnnotation.objects.select_for_update().filter(pk=annotation_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Annotation introuvable.")
        _assert_write_access(user, locked.session.athlete)
        _assert_annotation_allowed(locked.session)
        for field, value in data.items():
            setattr(locked, field, value)
        locked.save()
    return locked


def delete_annotation(user, annotation_pk: str) -> None:
    """Supprime une annotation (mêmes règles de statut que la création)."""
    from apps.sessions.models import SessionAnnotation

    with transaction.atomic():
        locked = SessionAnnotation.objects.select_for_update().filter(pk=annotation_pk).first()
        if locked is None:
            raise SessionsServiceError("not_found", "Annotation introuvable.")
        _assert_write_access(user, locked.session.athlete)
        _assert_annotation_allowed(locked.session)
        locked.delete()
