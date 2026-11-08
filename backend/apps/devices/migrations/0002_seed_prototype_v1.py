"""Seed du catalogue : le modèle ``prototype_v1`` (feature 04).

Choix documenté — migration de données plutôt que fixture :
- exécutée automatiquement par ``migrate`` dans TOUS les environnements
  (dev, tests, prod), sans étape ``loaddata`` à ne pas oublier ;
- idempotente : ``get_or_create`` sur ``(manufacturer, name)``, couple protégé
  par la contrainte d'unicité ``unique_device_model_manufacturer_name`` ;
- le catalogue est donc présent dès la première migration, y compris dans la
  base de tests (critère d'acceptation : enregistrer un capteur
  ``prototype_v1`` et le retrouver).

Les valeurs de ``capabilities`` sont des valeurs initiales provisoires : elles
seront ajustées sur le vrai capteur lors du spike matériel (feature 06b).
"""

from django.db import migrations


def seed_prototype_v1(apps, schema_editor):
    DeviceModel = apps.get_model("devices", "DeviceModel")
    DeviceModel.objects.get_or_create(
        manufacturer="EMG",
        name="prototype_v1",
        defaults={
            "protocol_version": 1,
            "connection_types": ["ble"],
            "capabilities": {
                "emg_channels_max": 8,
                "imu": False,
                "sample_rates": [250, 500, 1000],
                "resolution_bits": 16,
            },
        },
    )


def remove_prototype_v1(apps, schema_editor):
    DeviceModel = apps.get_model("devices", "DeviceModel")
    DeviceModel.objects.filter(manufacturer="EMG", name="prototype_v1").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("devices", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_prototype_v1, remove_prototype_v1),
    ]
