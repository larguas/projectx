"""Seed des guides de placement pour les muscles courants d'entraînement.

Même approche que le seed ``0003`` de l'app ``exercises`` :
- migration de données exécutée par ``migrate`` dans tous les environnements
  (dev, tests, prod), sans étape ``loaddata`` à ne pas oublier ;
- idempotente : ``get_or_create`` sur le muscle (OneToOne) — relancer la
  migration ne duplique rien ;
- un seul guide par muscle (``PlacementGuide.muscle`` est un OneToOneField).

Le seed des muscles (app ``exercises``) est déjà une dépendance transitive de
cette app (FK ``SetupChannel.muscle``), les codes sont donc garantis présents.

Conventions du contenu :
- texte en français, instructions courtes et factuelles de placement des
  électrodes (ventre musculaire, axe des fibres, espacement ~2 cm, référence
  osseuse proche), en appui des recommandations SENIAM ;
- ``reference`` commun citant SENIAM (Hermens et al., 2007) ;
- ``image`` volontairement NULL : les visuels seront ajoutés via l'admin.

Les muscles sans guide seedé restent sans guide : le endpoint
``GET /api/v1/muscles/{id}/placement-guide/`` retourne alors 404, ce qui est
attendu (le guide est optionnel par muscle).
"""

from django.db import migrations

# Référence citée par tous les guides (recommandations de placement normalisé).
REFERENCE = (
    "SENIAM — Hermens H.J., Freriks B., Disselhorst-Klug C., Rau G. (2007), "
    "« Surface Electromyography for the Non-Invasive Assessment of Muscles », "
    "J. NeuroEngineering and Rehabilitation"
)

# (code du muscle, titre, instructions courtes)
GUIDES = [
    (
        "biceps_brachii",
        "Placement des électrodes – Biceps brachial",
        "Deux électrodes sur le ventre musculaire, alignées dans l'axe du muscle "
        "(acromion → épicondyle latéral), espacées de 2 cm. Électrode de référence "
        "sur un os proche (acromion).",
    ),
    (
        "triceps_brachii",
        "Placement des électrodes – Triceps brachial",
        "Deux électrodes sur le chef latéral, alignées dans l'axe du muscle "
        "(acromion → olécrane), espacées de 2 cm. Référence près de l'olécrane.",
    ),
    (
        "deltoid",
        "Placement des électrodes – Deltoïde",
        "Deux électrodes sur le ventre de la tête moyenne, perpendiculaires à l'axe "
        "épaule-coude, espacées de 2 cm. Référence sur l'acromion.",
    ),
    (
        "pectoralis_major",
        "Placement des électrodes – Grand pectoral",
        "Deux électrodes sur le ventre musculaire, en dessous du sillon mammaire, "
        "alignées dans l'axe des fibres (clavicule → grande tubérosité), espacées "
        "de 2 cm. Référence sur la clavicule.",
    ),
    (
        "latissimus_dorsi",
        "Placement des électrodes – Grand dorsal",
        "Deux électrodes au tiers supérieur du ventre musculaire, près de la ligne "
        "axillaire postérieure, espacées de 2 cm dans l'axe des fibres. Référence "
        "sur le processus épineux d'une vertèbre thoracique.",
    ),
    (
        "rectus_abdominis",
        "Placement des électrodes – Grand droit de l'abdomen",
        "Deux électrodes verticales sur la ligne médiane, à mi-distance entre le "
        "nombril et le pubis, espacées de 2 cm. Référence sur une côte ou le pubis.",
    ),
    (
        "gluteus_maximus",
        "Placement des électrodes – Grand fessier",
        "Deux électrodes sur le ventre musculaire, espacées de 2 cm dans l'axe des "
        "fibres (crête iliaque → creux poplité). Référence sur la crête iliaque.",
    ),
    (
        "gluteus_medius",
        "Placement des électrodes – Moyen fessier",
        "Deux électrodes sur le ventre musculaire, sous la crête iliaque, espacées "
        "de 2 cm. Référence sur la crête iliaque.",
    ),
    (
        "rectus_femoris",
        "Placement des électrodes – Rectus fémoral",
        "Deux électrodes sur la ligne reliant l'épine iliaque antéro-supérieure au "
        "bord latéral du genou, espacées de 2 cm. Référence sur le grand trochanter.",
    ),
    (
        "vastus_lateralis",
        "Placement des électrodes – Vaste latéral",
        "Deux électrodes sur le ventre musculaire, à mi-distance entre le grand "
        "trochanter et le bord latéral du genou, espacées de 2 cm dans l'axe des "
        "fibres. Référence sur le grand trochanter.",
    ),
    (
        "vastus_medialis",
        "Placement des électrodes – Vaste médial",
        "Deux électrodes sur le ventre musculaire, en regard de la moitié inférieure "
        "du muscle, espacées de 2 cm. Référence sur la rotule.",
    ),
    (
        "biceps_femoris",
        "Placement des électrodes – Biceps fémoral",
        "Deux électrodes sur le ventre musculaire, à mi-distance entre l'épine "
        "ischiatique et le genou (face latérale), espacées de 2 cm. Référence sur "
        "une vertèbre lombaire ou la crête iliaque.",
    ),
    (
        "gastrocnemius",
        "Placement des électrodes – Gastrocnémien",
        "Deux électrodes sur le chef latéral, en bas du mollet, espacées de 2 cm "
        "dans l'axe des fibres. Référence sur la tête de la fibula.",
    ),
    (
        "tibialis_anterior",
        "Placement des électrodes – Tibial antérieur",
        "Deux électrodes sur le ventre musculaire, en avant de la jambe, espacées "
        "de 2 cm dans l'axe des fibres. Référence sur la crête tibiale.",
    ),
    (
        "peroneus_fibularis",
        "Placement des électrodes – Péronier",
        "Deux électrodes sur le ventre musculaire, face latérale de la jambe, "
        "espacées de 2 cm. Référence sur la tête de la fibula.",
    ),
]


def seed_guides(apps, schema_editor):
    """Crée (ou récupère) un guide par muscle seedé, idempotemment."""
    Muscle = apps.get_model("exercises", "Muscle")
    PlacementGuide = apps.get_model("setups", "PlacementGuide")

    for code, title, instructions in GUIDES:
        try:
            muscle = Muscle.objects.get(code=code)
        except Muscle.DoesNotExist:
            # Muscle absent (seed exercises non appliqué) : on passe sans bloquer.
            continue
        PlacementGuide.objects.get_or_create(
            muscle=muscle,
            defaults={
                "title": title,
                "instructions": instructions,
                "reference": REFERENCE,
            },
        )


def unseed_guides(apps, schema_editor):
    """Retire uniquement les guides seedés (inverse de ``seed_guides``)."""
    PlacementGuide = apps.get_model("setups", "PlacementGuide")
    PlacementGuide.objects.filter(muscle__code__in=[item[0] for item in GUIDES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("setups", "0002_sensorsetup_placement_inherited_from_parent"),
    ]

    operations = [
        migrations.RunPython(seed_guides, unseed_guides),
    ]
