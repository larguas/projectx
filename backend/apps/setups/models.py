"""Modèles de la feature 05b (app ``setups``).

- ``SensorSetup`` : placement déclaré d'un ou plusieurs capteurs pour un
  sportif, VERSIONNÉ. Tant qu'aucune séance ne l'utilise, il est modifiable
  librement ; dès qu'une séance l'utilise (feature 06), il est figé et toute
  modification crée une nouvelle version (``parent`` = version précédente).
  Unique ``(athlete, name, version)``.
- ``SetupChannel`` : un canal du placement — muscle visé + côté, et en mode
  ``detailed`` les champs détaillés (position, distance inter-électrodes,
  préparation cutanée, photo). ``muscle`` référence TOUJOURS
  ``exercises.Muscle`` (jamais ``MuscleGroup``, décision feature 05).
- ``PlacementGuide`` : guide de placement par muscle (un seul par muscle,
  seed SENIAM-style pour les muscles courants).
- ``Calibration`` : calibration (MVC / baseline repos) rattachée à une version
  PRÉCISE d'un setup et à un canal. Applicable si non invalidée, non expirée
  et rattachée au setup de la séance (cf.
  ``apps.setups.services.applicable_calibrations``).

Immutabilité des setups utilisés : la propriété ``SensorSetup.is_used`` est
portée par le marqueur ``used_at``, posé à la première utilisation par une
séance via une mise à jour en base ciblée (``objects.filter(...).update()``)
— qui ne passe PAS par ``save()`` — dans ``apps.sessions.services.create_session``
(feature 06), et vérifie aussi l'existence effective d'une séance référençant
le setup. Toute mutation (service ET ``save()`` modèle) refuse un setup avec
``is_used == True`` : un setup utilisé par une séance ne change jamais. Les
basculements d'état (``used_at``, ``is_current``) passent donc toujours par
des mises à jour en base ciblées, jamais par ``save()``.
"""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimestampedModel, UUIDModel


def _photo_path(instance, filename: str) -> str:
    """Nom de fichier aléatoire (aucune identité dans le chemin)."""
    return f"setups/photos/{uuid4().hex}{Path(filename).suffix.lower() or '.jpg'}"


class SensorSetup(TimestampedModel, UUIDModel):
    """Placement déclaré et versionné pour un sportif.

    ``detail_level`` : ``simple`` (muscle + côté par canal) ou ``detailed``
    (position, distance inter-électrodes, préparation cutanée, photo). Le
    niveau effectif est calculé en service : si aucun champ détaillé n'est
    renseigné sur les canaux, il est forcé à ``simple``.

    ``is_current`` marque la version courante d'un nom de setup (une seule
    par ``(athlete, name)`` — basculée par le service ``new_version``).
    """

    class DetailLevel(models.TextChoices):
        SIMPLE = "simple", "Simple"
        DETAILED = "detailed", "Détaillé"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif",
        on_delete=models.PROTECT,
        related_name="setups",
    )
    name = models.CharField("nom", max_length=200)
    version = models.PositiveIntegerField("version", default=1)
    parent = models.ForeignKey(
        "self",
        verbose_name="version précédente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_versions",
    )
    placement_inherited_from_parent = models.BooleanField(
        "placement hérité de la version précédente",
        default=False,
        help_text=(
            "True si cette version a été créée avec ``placement_unchanged=True`` : "
            "le placement est physiquement identique à la version parente. Base du "
            "niveau ``identical`` du service de comparaison."
        ),
    )
    detail_level = models.CharField(
        "niveau de détail",
        max_length=8,
        choices=DetailLevel.choices,
        default=DetailLevel.SIMPLE,
    )
    is_current = models.BooleanField("version courante", default=True)
    used_at = models.DateTimeField(
        "utilisé le",
        null=True,
        blank=True,
        help_text=(
            "Première utilisation par une séance (feature 06). Un setup utilisé "
            "est figé : toute modification passe par une nouvelle version."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="créateur",
        on_delete=models.CASCADE,
        related_name="setups_created",
    )
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "setup de placement"
        verbose_name_plural = "setups de placement"
        ordering = ("athlete", "name", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=("athlete", "name", "version"),
                name="unique_setup_version_per_athlete_name",
            )
        ]

    @property
    def is_used(self) -> bool:
        """Le setup est-il utilisé par au moins une séance ?

        Double vérification (feature 06) : le marqueur ``used_at`` — posé en
        base (mise à jour ciblée, pas de ``save()``) à la première utilisation
        par ``apps.sessions.services.create_session`` — OU l'existence
        effective d'une séance référençant ce setup (filet de sécurité : un
        setup référencé est figé même si le marqueur n'a pas été posé).
        """
        if self.used_at is not None:
            return True
        return self.sessions.exists()

    def assert_editable(self) -> None:
        """Refuse toute modification d'un setup figé (utilisé par une séance).

        Point de contrôle commun : appelé par ``save()`` (niveau MODÈLE) et
        par toutes les mutations de ``apps.setups.services`` (niveau SERVICE)
        — la spec exige cette double vérification. Les créations (``pk``
        vide) passent toujours.
        """
        if self.pk is not None and self.is_used:
            raise ValidationError(
                "Ce setup est utilisé par une séance et ne peut plus être modifié ; "
                "créez une nouvelle version (POST /setups/{id}/new-version/)."
            )

    def save(self, *args, **kwargs):
        self.assert_editable()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class SetupChannel(TimestampedModel, UUIDModel):
    """Un canal du placement : muscle + côté, champs détaillés optionnels.

    En mode ``simple`` seuls ``muscle`` et ``side`` sont renseignés ; en mode
    ``detailed`` s'ajoutent ``position_note``, ``inter_electrode_distance_mm``,
    ``skin_prep_done`` et ``photo`` (tous optionnels — le calcul du niveau est
    fait en service, cf. ``has_detailed_fields``).

    ``device`` est nullable : un canal peut être déclaré sans capteur précis
    (placement générique) ; la comparaison de setups utilise alors le modèle
    d'appareil des canaux qui en portent un.
    """

    class Side(models.TextChoices):
        LEFT = "left", "Gauche"
        RIGHT = "right", "Droite"
        NA = "na", "Non applicable"

    setup = models.ForeignKey(
        SensorSetup,
        verbose_name="setup",
        on_delete=models.CASCADE,
        related_name="channels",
    )
    device = models.ForeignKey(
        "devices.Device",
        verbose_name="capteur",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="setup_channels",
    )
    channel_id = models.PositiveIntegerField("canal du capteur")
    muscle = models.ForeignKey(
        "exercises.Muscle",
        verbose_name="muscle",
        on_delete=models.PROTECT,
        related_name="setup_channels",
    )
    side = models.CharField("côté", max_length=8, choices=Side.choices, default=Side.NA)
    position_note = models.TextField("note de position", blank=True)
    inter_electrode_distance_mm = models.PositiveIntegerField(
        "distance inter-électrodes (mm)", null=True, blank=True
    )
    skin_prep_done = models.BooleanField("préparation cutanée faite", null=True, blank=True)
    photo = models.FileField(
        "photo du placement",
        upload_to=_photo_path,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "canal de setup"
        verbose_name_plural = "canaux de setup"
        ordering = ("setup", "device_id", "channel_id")
        constraints = [
            models.UniqueConstraint(
                fields=("setup", "device", "channel_id"),
                name="unique_channel_per_setup_device",
            )
        ]

    @property
    def has_detailed_fields(self) -> bool:
        """Au moins un champ détaillé renseigné (position, distance, peau, photo)."""
        return bool(
            self.position_note
            or self.inter_electrode_distance_mm is not None
            or self.skin_prep_done is not None
            or self.photo
        )

    def __str__(self) -> str:
        return f"{self.setup} — canal {self.channel_id} ({self.muscle.code})"


class PlacementGuide(TimestampedModel, UUIDModel):
    """Guide de placement d'un muscle (un seul par muscle).

    Contenu court et factuel, référence citée (ex. recommandations SENIAM) ;
    seedé par une migration de données idempotente pour les muscles courants.
    Géré en admin, lu via ``GET /api/v1/muscles/{id}/placement-guide/``.
    """

    muscle = models.OneToOneField(
        "exercises.Muscle",
        verbose_name="muscle",
        on_delete=models.PROTECT,
        related_name="placement_guide",
    )
    title = models.CharField("titre", max_length=200)
    instructions = models.TextField("instructions")
    reference = models.CharField(
        "référence",
        max_length=300,
        help_text="Référence citée du guide (ex. recommandations SENIAM).",
    )
    image = models.FileField("image", upload_to="guides/", null=True, blank=True)

    class Meta:
        verbose_name = "guide de placement"
        verbose_name_plural = "guides de placement"
        ordering = ("muscle__code",)

    def __str__(self) -> str:
        return f"Guide {self.muscle.code}"


class Calibration(TimestampedModel, UUIDModel):
    """Calibration (MVC / baseline repos) d'un canal d'une version de setup.

    Rattachée à une version PRÉCISE du setup (``setup``) et à un canal
    (``setup_channel``) : une MVC n'a de sens que pour un placement donné.

    Applicable si — et seulement si — : non invalidée (``invalidated_at``
    vide), non expirée (``valid_until`` vide ou futur) ET rattachée au setup
    de la séance (condition vérifiée côté service par
    ``applicable_calibrations``, qui filtre sur le setup).

    ``source_session`` (FK nullable vers la séance de calibration d'origine,
    ajoutée en feature 06 — point ouvert du doc 05b clos ici) documente la
    provenance : la création effective de la Calibration depuis les signaux
    reste hors périmètre (feature 09, via le hook ``on_session_completed``).
    """

    class Type(models.TextChoices):
        MVC = "mvc", "Contraction maximale volontaire"
        REST_BASELINE = "rest_baseline", "Baseline au repos"

    athlete = models.ForeignKey(
        "athletes.AthleteProfile",
        verbose_name="sportif",
        on_delete=models.PROTECT,
        related_name="calibrations",
    )
    setup = models.ForeignKey(
        SensorSetup,
        verbose_name="setup",
        on_delete=models.PROTECT,
        related_name="calibrations",
    )
    setup_channel = models.ForeignKey(
        SetupChannel,
        verbose_name="canal de setup",
        on_delete=models.PROTECT,
        related_name="calibrations",
    )
    source_session = models.ForeignKey(
        "training_sessions.Session",
        verbose_name="séance de calibration d'origine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calibrations",
    )
    type = models.CharField("type", max_length=16, choices=Type.choices)
    values = models.JSONField(
        "valeurs",
        default=dict,
        help_text='JSON : mvc_rms, fenêtre, paramètres utilisés (ex. {"mvc_rms": 42.5}).',
    )
    algorithm_version = models.CharField("version d'algorithme", max_length=50, blank=True)
    valid_from = models.DateTimeField("valide depuis")
    valid_until = models.DateTimeField("valide jusqu'à", null=True, blank=True)
    invalidated_at = models.DateTimeField("invalidée le", null=True, blank=True)
    invalidation_reason = models.CharField("motif d'invalidation", max_length=300, blank=True)

    class Meta:
        verbose_name = "calibration"
        verbose_name_plural = "calibrations"
        ordering = ("-created_at",)

    @property
    def is_applicable(self) -> bool:
        """Non invalidée et non expirée.

        Le rattachement au setup de la séance (troisième condition de
        applicabilité) est vérifié par ``applicable_calibrations`` — qui
        filtre sur le setup — et non ici.
        """
        if self.invalidated_at is not None:
            return False
        if self.valid_until is not None and self.valid_until <= timezone.now():
            return False
        return True

    def __str__(self) -> str:
        return f"{self.get_type_display()} — {self.setup} / canal {self.setup_channel_id}"
