"""Seed de la bibliothèque : groupes, muscles et ~15 exercices courants.

Choix documenté — migration de données plutôt que fixture (même approche que
le seed ``prototype_v1`` de la feature 04) :
- exécutée automatiquement par ``migrate`` dans TOUS les environnements
  (dev, tests, prod), sans étape ``loaddata`` à ne pas oublier ;
- idempotente : ``get_or_create`` sur les champs uniques (``code`` des
  groupes/muscles, ``(name, is_global=True)`` des exercices,
  ``(exercise, muscle)`` des liens) — relancer la migration ne duplique rien ;
- le catalogue est donc présent dès la première migration, y compris dans la
  base de tests (critère d'acceptation : bibliothèque seedée consultable).

Conventions du contenu :
- ``code`` machine en snake_case minuscule (identifiant stable des API) ;
- noms d'affichage des groupes/muscles en français, ``latin_name`` en latin
  quand le nom anatomique existe (sinon NULL) ;
- noms d'exercices en anglais (nomenclature fitness internationale),
  descriptions en français (langue de la plateforme) ;
- les exercices seedés sont globaux (``is_global=True``, ``created_by=None``) :
  lecture pour tout utilisateur authentifié, écriture réservée au staff.

Les muscles ``tibialis_anterior`` et ``peroneus_fibularis`` ne sont reliés à
aucun exercice de ce premier lot : ils concernent la marche (feature 06) et
seront utilisés par les setups/canaux qui référencent ``Muscle`` directement.
"""

from django.db import migrations

# --- Données seedées -----------------------------------------------------------

# (code, nom d'affichage, région du corps)
GROUPS = [
    ("shoulder", "Épaule", "upper_limb"),
    ("upper_arm", "Bras", "upper_limb"),
    ("forearm", "Avant-bras", "upper_limb"),
    ("chest", "Poitrine", "trunk"),
    ("back", "Dos", "trunk"),
    ("abdomen", "Abdomen", "trunk"),
    ("glutes", "Fessiers", "trunk"),
    ("thigh", "Cuisse", "lower_limb"),
    ("calf", "Mollet", "lower_limb"),
    ("shin", "Tibia", "lower_limb"),
]

# (code, nom d'affichage, nom latin ou None, code du groupe, région, latéralisé)
MUSCLES = [
    ("deltoid", "Deltoïde", "Deltoid", "shoulder", "têtes antérieure, moyenne et postérieure", True),
    ("infraspinatus", "Infra-épineux", "Infraspinatus", "shoulder", "rotateur (postérieur)", True),
    ("supraspinatus", "Sus-épineux", "Supraspinatus", "shoulder", "rotateur (supérieur)", True),
    ("biceps_brachii", "Biceps brachial", "Biceps brachii", "upper_arm", "face antérieure du bras", True),
    ("triceps_brachii", "Triceps brachial", "Triceps brachii", "upper_arm", "face postérieure du bras", True),
    ("forearm_flexors", "Fléchisseurs du poignet", None, "forearm", "face antérieure de l'avant-bras", True),
    ("forearm_extensors", "Extenseurs du poignet", None, "forearm", "face postérieure de l'avant-bras", True),
    ("pectoralis_major", "Grand pectoral", "Pectoralis major", "chest", "paroi thoracique antérieure", True),
    ("pectoralis_minor", "Petit pectoral", "Pectoralis minor", "chest", "profond du grand pectoral", True),
    ("serratus_anterior", "Serrant antérieur", "Serratus anterior", "chest", "paroi thoracique latérale", True),
    ("latissimus_dorsi", "Grand dorsal", "Latissimus dorsi", "back", "dos inférieur", True),
    ("trapezius", "Trapèze", "Trapezius", "back", "dos supérieur / cou", True),
    ("rhomboids", "Rhomboïdes", "Rhomboidei", "back", "entre-omoplates", True),
    ("erector_spinae", "Érecteurs du rachis", "Erector spinae", "back", "paravertébral", True),
    ("rectus_abdominis", "Grand droit de l'abdomen", "Rectus abdominis", "abdomen", "ligne médiane antérieure", False),
    ("external_oblique", "Oblique externe", "Obliquus externus abdominis", "abdomen", "flanc", True),
    ("transversus_abdominis", "Transverse de l'abdomen", "Transversus abdominis", "abdomen", "profond du tronc", False),
    ("gluteus_maximus", "Grand fessier", "Gluteus maximus", "glutes", "fesse postérieure", True),
    ("gluteus_medius", "Moyen fessier", "Gluteus medius", "glutes", "fesse latérale", True),
    ("rectus_femoris", "Rectus fémoral", "Rectus femoris", "thigh", "cuisse antérieure", True),
    ("vastus_lateralis", "Vaste latéral", "Vastus lateralis", "thigh", "cuisse antéro-latérale", True),
    ("vastus_medialis", "Vaste médial", "Vastus medialis", "thigh", "cuisse antéro-médiale", True),
    ("vastus_intermedius", "Vaste intermédiaire", "Vastus intermedius", "thigh", "profond du rectus fémoral", True),
    ("biceps_femoris", "Biceps fémoral", "Biceps femoris", "thigh", "cuisse postérieure (ischio-jambier)", True),
    ("semitendinosus", "Semi-tendineux", "Semitendinosus", "thigh", "cuisse postérieure (ischio-jambier)", True),
    ("adductors", "Adducteurs de la hanche", None, "thigh", "cuisse médiale", True),
    ("gastrocnemius", "Gastrocnémien", "Gastrocnemius", "calf", "mollet postérieur (superficiel)", True),
    ("soleus", "Soleaire", "Soleus", "calf", "mollet postérieur (profond)", True),
    ("tibialis_anterior", "Tibial antérieur", "Tibialis anterior", "shin", "jambe antérieure", True),
    ("peroneus_fibularis", "Péronier", "Peroneus fibularis", "shin", "jambe latérale", True),
]

# (nom, description, type de mouvement, paramètres par défaut, [(code muscle, rôle)])
EXERCISES = [
    (
        "Bicep Curl",
        "Flexion du coude debout ou assis, charge dans les mains.",
        "isolation",
        {"target_reps": 12, "target_sets": 3},
        [("biceps_brachii", "primary"), ("forearm_flexors", "secondary")],
    ),
    (
        "Triceps Extension",
        "Extension du coude (poulie ou haltère) pour isoler le triceps.",
        "isolation",
        {"target_reps": 12, "target_sets": 3},
        [("triceps_brachii", "primary"), ("deltoid", "stabilizer")],
    ),
    (
        "Push-Up",
        "Pompes : flexion-extension des bras au poids du corps.",
        "compound",
        {"target_reps": 15, "target_sets": 3},
        [
            ("pectoralis_major", "primary"),
            ("triceps_brachii", "primary"),
            ("deltoid", "secondary"),
            ("serratus_anterior", "secondary"),
            ("rectus_abdominis", "stabilizer"),
        ],
    ),
    (
        "Bench Press",
        "Développé couché à la barre.",
        "compound",
        {"target_reps": 10, "target_sets": 4},
        [
            ("pectoralis_major", "primary"),
            ("triceps_brachii", "primary"),
            ("deltoid", "secondary"),
            ("serratus_anterior", "stabilizer"),
            ("pectoralis_minor", "stabilizer"),
        ],
    ),
    (
        "Pull-Up",
        "Tractions à la barre fixe.",
        "compound",
        {"target_reps": 8, "target_sets": 3},
        [
            ("latissimus_dorsi", "primary"),
            ("biceps_brachii", "secondary"),
            ("rhomboids", "secondary"),
            ("trapezius", "secondary"),
        ],
    ),
    (
        "Squat",
        "Squat barre sur l'épaule.",
        "compound",
        {"target_reps": 10, "target_sets": 4},
        [
            ("rectus_femoris", "primary"),
            ("vastus_lateralis", "primary"),
            ("vastus_medialis", "primary"),
            ("gluteus_maximus", "secondary"),
            ("erector_spinae", "stabilizer"),
            ("gluteus_medius", "stabilizer"),
        ],
    ),
    (
        "Leg Press",
        "Presse à cuisses.",
        "compound",
        {"target_reps": 12, "target_sets": 3},
        [
            ("rectus_femoris", "primary"),
            ("vastus_lateralis", "primary"),
            ("vastus_medialis", "primary"),
            ("gluteus_maximus", "secondary"),
            ("adductors", "stabilizer"),
        ],
    ),
    (
        "Romanian Deadlift",
        "Soulevé de terre roumain : charnière hanche, genoux semi-fléchis.",
        "compound",
        {"target_reps": 10, "target_sets": 3},
        [
            ("biceps_femoris", "primary"),
            ("semitendinosus", "primary"),
            ("gluteus_maximus", "secondary"),
            ("erector_spinae", "secondary"),
        ],
    ),
    (
        "Leg Curl",
        "Leg curl allongé ou assis.",
        "isolation",
        {"target_reps": 12, "target_sets": 3},
        [
            ("biceps_femoris", "primary"),
            ("semitendinosus", "primary"),
            ("gastrocnemius", "stabilizer"),
        ],
    ),
    (
        "Calf Raise",
        "Extensions de cheville en charge (mollets).",
        "isolation",
        {"target_reps": 15, "target_sets": 4},
        [("gastrocnemius", "primary"), ("soleus", "primary")],
    ),
    (
        "Plank",
        "Planche gainage : contraction isométrique du tronc.",
        "isometric",
        {"target_sets": 3, "hold_seconds": 30},
        [
            ("rectus_abdominis", "primary"),
            ("external_oblique", "secondary"),
            ("transversus_abdominis", "secondary"),
            ("gluteus_maximus", "stabilizer"),
        ],
    ),
    (
        "Deadlift",
        "Soulevé de terre conventionnel.",
        "compound",
        {"target_reps": 6, "target_sets": 4},
        [
            ("erector_spinae", "primary"),
            ("gluteus_maximus", "primary"),
            ("biceps_femoris", "secondary"),
            ("latissimus_dorsi", "secondary"),
            ("trapezius", "secondary"),
            ("rectus_abdominis", "stabilizer"),
        ],
    ),
    (
        "Lateral Raise",
        "Élévations latérales haltères, coudes légèrement fléchis.",
        "isolation",
        {"target_reps": 12, "target_sets": 3},
        [
            ("deltoid", "primary"),
            ("infraspinatus", "secondary"),
            ("supraspinatus", "secondary"),
        ],
    ),
    (
        "Shoulder Press",
        "Développé militaire debout.",
        "compound",
        {"target_reps": 10, "target_sets": 3},
        [
            ("deltoid", "primary"),
            ("triceps_brachii", "secondary"),
            ("serratus_anterior", "stabilizer"),
        ],
    ),
    (
        "Leg Extension",
        "Extension de jambe à la machine.",
        "isolation",
        {"target_reps": 12, "target_sets": 3},
        [
            ("rectus_femoris", "primary"),
            ("vastus_lateralis", "primary"),
            ("vastus_medialis", "primary"),
            ("vastus_intermedius", "secondary"),
        ],
    ),
]


def seed_library(apps, schema_editor):
    """Crée (ou récupère) le catalogue, idempotemment."""
    MuscleGroup = apps.get_model("exercises", "MuscleGroup")
    Muscle = apps.get_model("exercises", "Muscle")
    Exercise = apps.get_model("exercises", "Exercise")
    ExerciseMuscle = apps.get_model("exercises", "ExerciseMuscle")

    groups: dict[str, object] = {}
    for code, name, body_region in GROUPS:
        group, _created = MuscleGroup.objects.get_or_create(
            code=code, defaults={"name": name, "body_region": body_region}
        )
        groups[code] = group

    muscles: dict[str, object] = {}
    for code, name, latin_name, group_code, region, side_relevant in MUSCLES:
        muscle, _created = Muscle.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "latin_name": latin_name,
                "muscle_group": groups[group_code],
                "region": region,
                "side_relevant": side_relevant,
            },
        )
        muscles[code] = muscle

    for name, description, movement_type, default_parameters, links in EXERCISES:
        exercise, _created = Exercise.objects.get_or_create(
            name=name,
            is_global=True,
            defaults={
                "description": description,
                "movement_type": movement_type,
                "default_parameters": default_parameters,
            },
        )
        for muscle_code, role in links:
            ExerciseMuscle.objects.get_or_create(
                exercise=exercise,
                muscle=muscles[muscle_code],
                defaults={"role": role},
            )


def unseed_library(apps, schema_editor):
    """Retire uniquement les lignes seedées (inverse de ``seed_library``)."""
    MuscleGroup = apps.get_model("exercises", "MuscleGroup")
    Muscle = apps.get_model("exercises", "Muscle")
    Exercise = apps.get_model("exercises", "Exercise")

    # Les liens ExerciseMuscle sont supprimés en cascade avec les exercices.
    Exercise.objects.filter(name__in=[item[0] for item in EXERCISES], is_global=True).delete()
    Muscle.objects.filter(code__in=[item[0] for item in MUSCLES]).delete()
    MuscleGroup.objects.filter(code__in=[item[0] for item in GROUPS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0002_alter_exercise_movement_type"),
    ]

    operations = [
        migrations.RunPython(seed_library, unseed_library),
    ]
