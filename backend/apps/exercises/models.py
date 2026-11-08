"""Modèles de la feature 05 (app ``exercises``).

Taxonomie en deux niveaux (revue de roadmap « niveau muscle ») :
- ``MuscleGroup`` : groupe musculaire grossier (code machine, nom, région du
  corps) ;
- ``Muscle`` : muscle précis (biceps brachii, vastus lateralis…), rattaché à
  son groupe. Les features 05b (setups) et 06 (canaux de séance) référencent
  ``Muscle``, jamais ``MuscleGroup`` directement.

Bibliothèque d'exercices :
- ``Exercise`` : exercice global (bibliothèque partagée, ``is_global=True``,
  écriture réservée au staff) ou personnel (``is_global=False``, visible et
  éditable par son créateur uniquement) ;
- ``ExerciseMuscle`` : table intermédiaire portant le rôle du muscle dans
  l'exercice (``primary`` / ``secondary`` / ``stabilizer``).

Les catalogues (groupes, muscles) sont gérés en admin et seedés par une
migration de données idempotente ; les utilisateurs n'y ont accès qu'en
lecture seule via l'API.
"""

from django.conf import settings
from django.db import models

from core.models import TimestampedModel, UUIDModel


class MuscleGroup(TimestampedModel, UUIDModel):
    """Groupe musculaire grossier (ex. « bras », « cuisse »).

    ``code`` est l'identifiant machine stable (snake_case, unique) ; ``name``
    est le nom d'affichage. ``body_region`` est la région du corps au sens
    large (convention : snake_case, ex. ``upper_limb``, ``lower_limb``,
    ``trunk``).
    """

    code = models.CharField("code", max_length=50, unique=True)
    name = models.CharField("nom", max_length=100)
    body_region = models.CharField(
        "région du corps",
        max_length=50,
        help_text="Région au sens large (convention snake_case : upper_limb, lower_limb, trunk…).",
    )

    class Meta:
        verbose_name = "groupe musculaire"
        verbose_name_plural = "groupes musculaires"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.name


class Muscle(TimestampedModel, UUIDModel):
    """Muscle précis référencé par les exercices (et, plus tard, setups/canaux).

    ``code`` est l'identifiant machine stable (snake_case, unique) ;
    ``latin_name`` est le nom anatomique latin (nullable). ``region`` précise
    la localisation du muscle au sein de son groupe (ex. face antérieure de la
    cuisse). ``side_relevant`` indique que le muscle existe en version
    gauche/droite (essentiel pour le placement des capteurs, feature 05b/06) ;
    un muscle médian (rectus abdominis) a ``side_relevant=False``.
    """

    code = models.CharField("code", max_length=50, unique=True)
    name = models.CharField("nom", max_length=100)
    # Nullable d'après la spec (feature 05) ; DJ001 recommande la chaîne vide
    # mais le NULL base est ici sémantiquement significatif (« nom latin inconnu »).
    latin_name = models.CharField(  # noqa: DJ001
        "nom latin", max_length=150, null=True, blank=True
    )
    muscle_group = models.ForeignKey(
        MuscleGroup,
        verbose_name="groupe musculaire",
        on_delete=models.PROTECT,
        related_name="muscles",
    )
    region = models.CharField(
        "région",
        max_length=100,
        blank=True,
        help_text="Localisation précise au sein du groupe (ex. face antérieure de la cuisse).",
    )
    side_relevant = models.BooleanField(
        "latéralisé",
        default=True,
        help_text="Le muscle a une version gauche/droite (False pour les muscles médians).",
    )

    class Meta:
        verbose_name = "muscle"
        verbose_name_plural = "muscles"
        ordering = ("muscle_group__code", "code")
        constraints = [
            models.UniqueConstraint(
                fields=("muscle_group", "name"), name="unique_muscle_name_per_group"
            )
        ]

    def __str__(self) -> str:
        return self.name


class Exercise(TimestampedModel, UUIDModel):
    """Exercice de la bibliothèque (globale ou personnelle).

    - ``is_global=True`` : exercice de la bibliothèque partagée, lisible par
      tout utilisateur authentifié, écriture réservée au staff (Django
      ``is_staff`` — administrateur plateforme, cf. ``accounts.User``) ;
    - ``is_global=False`` : exercice personnel, créé et visible/modifiable par
      son créateur (``created_by``) uniquement.

    ``default_parameters`` est un JSON documentant les paramètres par défaut
    de l'exercice (forme attendue par la plateforme ::

        {"target_reps": 10, "target_sets": 3, "tempo": "3-1-2"}

    ). Les muscles sollicités sont portés par ``ExerciseMuscle`` avec un rôle.
    """

    class MovementType(models.TextChoices):
        COMPOUND = "compound", "Polyarticulaire"
        ISOLATION = "isolation", "Monoarticulaire"
        ISOMETRIC = "isometric", "Isométrique"

    name = models.CharField("nom", max_length=200)
    description = models.TextField("description", blank=True)
    movement_type = models.CharField(
        "type de mouvement",
        max_length=16,
        choices=MovementType.choices,
        default=MovementType.COMPOUND,
    )
    default_parameters = models.JSONField(
        "paramètres par défaut",
        default=dict,
        help_text='JSON : reps cibles, séries, tempo… (ex. {"target_reps": 10}).',
    )
    is_global = models.BooleanField("global", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="créateur",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="exercises",
    )
    is_archived = models.BooleanField("archivé", default=False)
    muscles = models.ManyToManyField(
        Muscle,
        through="ExerciseMuscle",
        related_name="exercises",
    )

    class Meta:
        verbose_name = "exercice"
        verbose_name_plural = "exercices"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class ExerciseMuscle(TimestampedModel, UUIDModel):
    """Rôle d'un muscle dans un exercice (table intermédiaire).

    Un muscle ne peut jouer qu'UN rôle par exercice (contrainte d'unicité sur
    ``(exercise, muscle)``) : ``primary`` (cible principale), ``secondary``
    (aide la cible) ou ``stabilizer`` (maintient l'équilibre sans être ciblé).
    """

    class Role(models.TextChoices):
        PRIMARY = "primary", "Principal"
        SECONDARY = "secondary", "Secondaire"
        STABILIZER = "stabilizer", "Stabilisateur"

    exercise = models.ForeignKey(
        Exercise,
        verbose_name="exercice",
        on_delete=models.CASCADE,
        related_name="muscle_links",
    )
    muscle = models.ForeignKey(
        Muscle,
        verbose_name="muscle",
        on_delete=models.CASCADE,
        related_name="exercise_links",
    )
    role = models.CharField("rôle", max_length=12, choices=Role.choices, default=Role.PRIMARY)

    class Meta:
        verbose_name = "muscle d'un exercice"
        verbose_name_plural = "muscles des exercices"
        ordering = ("exercise__name", "role")
        constraints = [
            models.UniqueConstraint(
                fields=("exercise", "muscle"), name="unique_muscle_per_exercise"
            )
        ]

    def __str__(self) -> str:
        return f"{self.exercise} — {self.muscle} ({self.role})"
