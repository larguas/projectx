"""Modèles de la feature 06 (app ``sessions``).

- ``Session`` : une séance d'acquisition — l'objet auquel se rattachent les
  données, les analyses, les annotations et les rapports. Machine à états::

      created → recording → completed
      created → cancelled
      recording → cancelled | failed

  Toute autre transition est refusée (409) par les services de
  ``apps.sessions.services`` (avec verrouillage ``select_for_update``) ; le
  statut n'est JAMAIS modifié depuis un serializer.
- ``SessionDevice`` : un appareil utilisé dans la séance, avec un rôle
  (``primary`` / ``secondary``, au plus un primaire par séance). Une séance peut
  utiliser PLUSIEURS appareils — il n'y a plus de FK unique vers un capteur ;
  ``(session, device)`` est unique. ``clock_offset_ms`` (décalage par rapport à
  l'horloge de l'appareil primaire) sera estimé en feature 07.
- ``SessionChannel`` : un canal de la séance, figé depuis le placement d'un
  setup (feature 05b — muscle et côté figés) ou déclaré à la main. ``device``
  est OBLIGATOIRE sur chaque canal ; ``(session, device, channel_id)`` est
  unique — les canaux de chaque appareil sont distincts.
- ``SessionAnnotation`` : annotation / marqueur rattaché à une séance (bornes
  de séries et de répétitions, notes, artefacts, impulsions de synchronisation),
  positionnée par ``offset_ms`` par rapport au début d'acquisition (horloge de
  l'appareil primaire). Tri par ``offset_ms``.

Nom d'app : ``label = "training_sessions"`` — ``sessions`` entre en conflit
avec ``django.contrib.sessions`` (décision n°2, cf. ``docs/00-index.md``) ; les
FK inter-apps pointent vers ``"training_sessions.Session"``.
"""

from django.conf import settings
from django.db import models

from core.models import TimestampedModel, UUIDModel


class Session(TimestampedModel, UUIDModel):
    """Séance d'acquisition (machine à états + placement figé).

    ``setup`` référence une version PRÉCISE du placement déclaré : elle devient
    IMMUABLE dès qu'une séance l'utilise (feature 05b — point d'extension posé
    par ``apps.sessions.services.create_session`` via une mise à jour en base
    ciblée, jamais de ``save()``). Sans setup, ``setup_declared = False`` et
    l'API renvoie un avertissement ``setup_not_declared`` (réponse ET détail).

    Une séance ``calibration`` exige un ``setup`` ET un ``calibration_type``
    (validation à la création — une calibration sans placement connu n'est pas
    exploitable).

    Le statut suit UNIQUEMENT la machine à états ci-dessous ; les transitions
    passent par les services dédiés (``start_session`` / ``complete_session`` /
    ``cancel_session`` / ``fail_session``), jamais par un serializer.
    """

    class SessionType(models.TextChoices):
        TRAINING = "training", "Entraînement"
        CALIBRATION = "calibration", "Calibration"
        TEST = "test", "Test"

    class Status(models.TextChoices):
        CREATED = "created", "Créée"
        RECORDING = "recording", "Enregistrement"
        COMPLETED = "completed", "Terminée"
        CANCELLED = "cancelled", "Annulée"
        FAILED = "failed", "Échouée"

    class Source(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        PC = "pc", "PC"
        IMPORT = "import", "Import"

    # Transitions autorisées par la machine à états — toute autre transition
    # est refusée (409) par les services. Les états terminaux n'apparaissent
    # pas comme clés : aucune transition n'en sort.
    TRANSITIONS: dict[str, tuple[str, ...]] = {
        Status.CREATED: (Status.RECORDING, Status.CANCELLED),
        Status.RECORDING: (Status.COMPLETED, Status.CANCELLED, Status.FAILED),
    }

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="créateur",
        on_delete=models.CASCADE,
        related_name="sessions_created",
    )
    session_type = models.CharField("type de séance", max_length=12, choices=SessionType.choices)
    setup = models.ForeignKey(
        "setups.SensorSetup",
        verbose_name="setup de placement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
    )
    setup_declared = models.BooleanField(
        "placement déclaré",
        default=False,
        help_text=(
            "False si la séance a été créée sans setup : l'API renvoie alors un "
            "avertissement ``setup_not_declared`` (réponse et détail)."
        ),
    )
    exercise = models.ForeignKey(
        "exercises.Exercise",
        verbose_name="exercice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
    )
    workout = models.ForeignKey(
        "workouts.Workout",
        verbose_name="plan d'entraînement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sessions",
    )
    status = models.CharField(
        "statut", max_length=12, choices=Status.choices, default=Status.CREATED
    )
    source = models.CharField("source", max_length=8, choices=Source.choices, default=Source.MOBILE)
    protocol_version = models.PositiveIntegerField("version du protocole", default=1)
    started_at = models.DateTimeField("démarrée le", null=True, blank=True)
    ended_at = models.DateTimeField("terminée le", null=True, blank=True)
    notes = models.TextField("notes", blank=True)
    acquisition_config = models.JSONField(
        "configuration d'acquisition",
        default=dict,
        blank=True,
        help_text="JSON : sample_rate prévu, canaux, paramètres d'acquisition.",
    )
    # NULL base : « pas de type de calibration » n'a pas de sens avec une chaîne
    # vide — le champ n'est rempli QUE pour les séances de calibration.
    calibration_type = models.CharField(  # noqa: DJ001
        "type de calibration",
        max_length=16,
        choices=[
            ("mvc", "Contraction maximale volontaire"),
            ("rest_baseline", "Baseline au repos"),
        ],
        null=True,
        blank=True,
        help_text="Requis si ``session_type = calibration`` (mêmes valeurs que Calibration.type).",
    )

    class Meta:
        verbose_name = "séance"
        verbose_name_plural = "séances"
        ordering = ("-created_at",)

    def can_transition_to(self, target_status: str) -> bool:
        """La machine à états autorise-t-elle la transition vers ``target_status`` ?"""
        return target_status in self.TRANSITIONS.get(self.status, ())

    @property
    def is_terminal(self) -> bool:
        """État terminal (completed / cancelled / failed) : plus aucune transition."""
        return not self.TRANSITIONS.get(self.status)

    def __str__(self) -> str:
        return f"Séance {self.session_type} — {self.athlete_id} ({self.status})"


class SessionDevice(TimestampedModel, UUIDModel):
    """Un appareil utilisé dans une séance (support multi-appareils).

    Rôle ``primary`` / ``secondary`` : au plus un appareil primaire par séance
    (l'horloge de référence des annotations est celle du primaire). Le décalage
    d'horloge ``clock_offset_ms`` des appareils secondaires sera estimé en
    feature 07 (réception des blocs de données).
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Primaire"
        SECONDARY = "secondary", "Secondaire"

    session = models.ForeignKey(
        Session,
        verbose_name="séance",
        on_delete=models.CASCADE,
        related_name="devices",
    )
    device = models.ForeignKey(
        "devices.Device",
        verbose_name="capteur",
        on_delete=models.PROTECT,
        related_name="session_devices",
    )
    role = models.CharField("rôle", max_length=10, choices=Role.choices, default=Role.PRIMARY)
    clock_offset_ms = models.IntegerField(
        "décalage d'horloge (ms)",
        null=True,
        blank=True,
        help_text="Offset estimé par rapport à l'horloge de l'appareil primaire (feature 07).",
    )

    class Meta:
        verbose_name = "appareil de séance"
        verbose_name_plural = "appareils de séance"
        ordering = ("session", "role", "device_id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "device"),
                name="unique_device_per_session",
            )
        ]

    def __str__(self) -> str:
        return f"{self.session} — {self.device_id} ({self.role})"


class SessionChannel(TimestampedModel, UUIDModel):
    """Un canal de la séance : figé depuis le placement d'un setup ou déclaré à la main.

    ``device`` est OBLIGATOIRE sur chaque canal (il n'y a pas de canal « sans
    capteur » en acquisition) ; les canaux de chaque appareil sont DISTINCTS —
    ``(session, device, channel_id)`` est unique. Copié depuis un setup
    (feature 05b), ``muscle`` et ``side`` sont FIGÉS et ``setup_channel`` garde
    la référence au canal du placement d'origine. ``calibration`` est une copie
    figée des informations de calibration utiles pour ce canal.
    """

    class Side(models.TextChoices):
        LEFT = "left", "Gauche"
        RIGHT = "right", "Droite"
        NA = "na", "Non applicable"

    class DataType(models.TextChoices):
        EMG_RAW = "emg_raw", "EMG brut"
        EMG_ENVELOPE = "emg_envelope", "Enveloppe EMG"
        IMU_ACCEL = "imu_accel", "Accéléromètre"
        IMU_GYRO = "imu_gyro", "Gyroscope"

    session = models.ForeignKey(
        Session,
        verbose_name="séance",
        on_delete=models.CASCADE,
        related_name="channels",
    )
    device = models.ForeignKey(
        "devices.Device",
        verbose_name="capteur",
        on_delete=models.PROTECT,
        related_name="session_channels",
    )
    channel_id = models.PositiveIntegerField("canal du capteur")
    muscle = models.ForeignKey(
        "exercises.Muscle",
        verbose_name="muscle",
        on_delete=models.PROTECT,
        related_name="session_channels",
    )
    side = models.CharField("côté", max_length=8, choices=Side.choices, default=Side.NA)
    data_type = models.CharField(
        "type de donnée", max_length=16, choices=DataType.choices, default=DataType.EMG_RAW
    )
    units = models.CharField("unités", max_length=32, blank=True)
    calibration = models.JSONField(
        "calibration (copie figée)",
        null=True,
        blank=True,
        help_text="Copie figée des informations de calibration utiles pour ce canal.",
    )
    setup_channel = models.ForeignKey(
        "setups.SetupChannel",
        verbose_name="canal de setup d'origine",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="session_channels",
    )

    class Meta:
        verbose_name = "canal de séance"
        verbose_name_plural = "canaux de séance"
        ordering = ("session", "device_id", "channel_id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "device", "channel_id"),
                name="unique_channel_per_session_device",
            )
        ]

    def __str__(self) -> str:
        return f"{self.session} — canal {self.channel_id} ({self.muscle.code})"


class SessionAnnotation(UUIDModel):
    """Annotation / marqueur rattaché à une séance.

    ``offset_ms`` positionne l'annotation par rapport au début d'acquisition
    (horloge de l'appareil primaire) ; la liste est triée par ``offset_ms``.
    Les annotations sont autorisées PENDANT ``recording`` et APRÈS
    ``completed`` (corrections du coach), JAMAIS sur une séance ``cancelled`` —
    contrôle dans ``apps.sessions.services``.
    """

    class Kind(models.TextChoices):
        SET_START = "set_start", "Début de série"
        SET_END = "set_end", "Fin de série"
        REP_START = "rep_start", "Début de répétition"
        REP_END = "rep_end", "Fin de répétition"
        NOTE = "note", "Note"
        ARTIFACT = "artifact", "Artefact"
        SYNC_PULSE = "sync_pulse", "Impulsion de synchronisation"

    session = models.ForeignKey(
        Session,
        verbose_name="séance",
        on_delete=models.CASCADE,
        related_name="annotations",
    )
    kind = models.CharField("type", max_length=16, choices=Kind.choices)
    offset_ms = models.IntegerField("décalage (ms)")
    text = models.TextField("texte", blank=True)
    metadata = models.JSONField("métadonnées", default=dict, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="auteur",
        on_delete=models.CASCADE,
        related_name="session_annotations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "annotation de séance"
        verbose_name_plural = "annotations de séance"
        ordering = ("offset_ms", "created_at")

    def __str__(self) -> str:
        return f"{self.session} — {self.kind} @ {self.offset_ms} ms"
