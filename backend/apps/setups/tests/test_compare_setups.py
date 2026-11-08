"""Matrice exhaustive de ``compare_setups`` (doc 05b, spec §8.5).

Cinq niveaux : ``identical`` / ``equivalent`` / ``approximate`` /
``different`` / ``unknown``. Pour chaque cas on vérifie le niveau ET la forme
de ``reasons`` (liste non vide de chaînes lisibles — l'IA les réutilisera
comme caveats, feature 12).

Les cas de lignée sont construits par les services réels (``mark_used`` +
``new_version``) : les données testées (``parent``,
``placement_inherited_from_parent``) sont exactement celles que produit la
production. Les autres cas passent par ``set_channels`` pour que le
``detail_level`` soit recalculé comme en production.
"""

from apps.athletes.tests.factories import AthleteProfileFactory
from apps.devices.tests.factories import DeviceFactory, DeviceModelFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.setups import services
from apps.setups.models import SensorSetup
from apps.setups.tests.factories import SensorSetupFactory, mark_used


def _check(result: dict, level: str) -> dict:
    """Asserte le niveau et la forme de ``reasons`` ; retourne le résultat."""
    assert result["level"] == level
    assert isinstance(result["reasons"], list)
    assert all(isinstance(r, str) and r for r in result["reasons"])
    return result


def _build(athlete, name: str, specs: list) -> SensorSetup:
    """Crée un setup avec ses canaux via ``set_channels`` (recalcule le niveau).

    ``specs`` : liste de dicts — ``muscle`` requis ; optionnels ``side``,
    ``channel_id``, ``distance``, ``position_note``, ``device``.
    """
    setup = SensorSetupFactory(athlete=athlete, name=name)
    entries = [
        {
            "device": spec.get("device"),
            "channel_id": spec.get("channel_id", index + 1),
            "muscle": spec["muscle"],
            "side": spec.get("side", "left"),
            "position_note": spec.get("position_note", ""),
            "inter_electrode_distance_mm": spec.get("distance"),
        }
        for index, spec in enumerate(specs)
    ]
    services.set_channels(athlete.user, setup, entries)
    return setup


def _detailed_specs(muscles: list, devices: list, distance: int = 20) -> list:
    """Canaux détaillés alignés (position + distance + capteur sur chaque canal)."""
    return [
        {
            "muscle": muscle,
            "side": "left" if index % 2 == 0 else "right",
            "distance": distance,
            "position_note": f"1/3 bas du ventre du muscle ({index})",
            "device": device,
        }
        for index, (muscle, device) in enumerate(zip(muscles, devices, strict=True))
    ]


class TestUnknown:
    """L'un des deux setups est absent (introuvable ou non visible)."""

    def test_a_missing(self):
        setup = _build(AthleteProfileFactory(), "Bras", [{"muscle": MuscleFactory()}])
        assert _check(services.compare_setups(None, setup), "unknown")

    def test_b_missing(self):
        setup = _build(AthleteProfileFactory(), "Bras", [{"muscle": MuscleFactory()}])
        assert _check(services.compare_setups(setup, None), "unknown")

    def test_both_missing(self):
        assert _check(services.compare_setups(None, None), "unknown")


class TestIdentical:
    """Même version, ou même lignée sans modification du placement."""

    def test_same_setup_object(self):
        setup = _build(AthleteProfileFactory(), "Bras", [{"muscle": MuscleFactory()}])
        result = _check(services.compare_setups(setup, setup), "identical")
        assert any("même version" in r for r in result["reasons"])

    def test_lineage_placement_unchanged(self):
        athlete = AthleteProfileFactory()
        v1 = _build(athlete, "Bras", [{"muscle": MuscleFactory()}])
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": True})
        assert _check(services.compare_setups(v1, v2), "identical")

    def test_lineage_order_does_not_matter(self):
        athlete = AthleteProfileFactory()
        v1 = _build(athlete, "Bras", [{"muscle": MuscleFactory()}])
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": True})
        assert _check(services.compare_setups(v2, v1), "identical")

    def test_lineage_chain_all_unchanged(self):
        athlete = AthleteProfileFactory()
        v1 = _build(athlete, "Bras", [{"muscle": MuscleFactory()}])
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": True})
        v3 = services.new_version(athlete.user, mark_used(v2), {"placement_unchanged": True})
        assert _check(services.compare_setups(v1, v3), "identical")


class TestDifferent:
    """Correspondance muscle/côté différente."""

    def test_different_muscle(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        a = _build(athlete, "Bras A", [{"muscle": m1}])
        b = _build(athlete, "Bras B", [{"muscle": m2}])
        result = _check(services.compare_setups(a, b), "different")
        assert any(m1.code in r and m2.code in r for r in result["reasons"])

    def test_different_side(self):
        athlete = AthleteProfileFactory()
        muscle = MuscleFactory()
        a = _build(athlete, "Bras A", [{"muscle": muscle, "side": "left"}])
        b = _build(athlete, "Bras B", [{"muscle": muscle, "side": "right"}])
        result = _check(services.compare_setups(a, b), "different")
        assert any("left" in r and "right" in r for r in result["reasons"])

    def test_different_channel_count(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        a = _build(athlete, "Bras A", [{"muscle": m1}, {"muscle": m2}])
        b = _build(athlete, "Bras B", [{"muscle": m1}])
        assert _check(services.compare_setups(a, b), "different")


class TestApproximate:
    """Même correspondance muscle/côté, mais niveau de détail ou mesures non alignés."""

    def test_both_simple_same_mapping(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        specs = [{"muscle": m1}, {"muscle": m2}]
        a = _build(athlete, "Bras A", specs)
        b = _build(athlete, "Bras B", specs)
        assert a.detail_level == SensorSetup.DetailLevel.SIMPLE
        result = _check(services.compare_setups(a, b), "approximate")
        assert any("mode simple" in r for r in result["reasons"])

    def test_one_simple_one_detailed(self):
        athlete = AthleteProfileFactory()
        muscle = MuscleFactory()
        a = _build(athlete, "Bras A", [{"muscle": muscle}])
        b = _build(
            athlete,
            "Bras B",
            [{"muscle": muscle, "position_note": "1/3 bas du ventre"}],
        )
        assert _check(services.compare_setups(a, b), "approximate")

    def test_detailed_distances_differ(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices_a = [DeviceFactory(device_model=model) for _ in range(2)]
        devices_b = [DeviceFactory(device_model=model) for _ in range(2)]
        a = _build(athlete, "Bras A", _detailed_specs([m1, m2], devices_a, distance=20))
        b_specs = _detailed_specs([m1, m2], devices_b, distance=20)
        b_specs[0]["distance"] = 25
        b = _build(athlete, "Bras B", b_specs)
        result = _check(services.compare_setups(a, b), "approximate")
        assert any("distance" in r.lower() for r in result["reasons"])

    def test_detailed_device_models_differ(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        devices_a = [DeviceFactory(device_model=DeviceModelFactory()) for _ in range(2)]
        devices_b = [DeviceFactory(device_model=DeviceModelFactory()) for _ in range(2)]
        a = _build(athlete, "Bras A", _detailed_specs([m1, m2], devices_a))
        b = _build(athlete, "Bras B", _detailed_specs([m1, m2], devices_b))
        result = _check(services.compare_setups(a, b), "approximate")
        assert any("modèle" in r.lower() for r in result["reasons"])

    def test_detailed_device_not_declared_on_one_channel(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices_a = [DeviceFactory(device_model=model) for _ in range(2)]
        b_specs = _detailed_specs([m1, m2], [devices_a[0], None])
        a = _build(athlete, "Bras A", _detailed_specs([m1, m2], devices_a))
        b = _build(athlete, "Bras B", b_specs)
        result = _check(services.compare_setups(a, b), "approximate")
        assert any("non déclaré" in r for r in result["reasons"])


class TestEquivalent:
    """Deux setups détaillés pleinement alignés (muscle/côté, distances, modèles)."""

    def test_detailed_fully_aligned(self):
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices_a = [DeviceFactory(device_model=model) for _ in range(2)]
        devices_b = [DeviceFactory(device_model=model) for _ in range(2)]
        a = _build(athlete, "Bras A", _detailed_specs([m1, m2], devices_a))
        # Notes de position volontairement différentes : elles ne comptent pas.
        b_specs = _detailed_specs([m1, m2], devices_b)
        b_specs[0]["position_note"] = "autre formulation"
        b = _build(athlete, "Bras B", b_specs)
        assert _check(services.compare_setups(a, b), "equivalent")

    def test_lineage_placement_changed_but_channels_aligned(self):
        """Interprétation documentée : même lignée mais placement modifié →
        la comparaison retombe sur les canaux (ici alignés)."""
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices = [DeviceFactory(device_model=model) for _ in range(2)]
        v1 = _build(athlete, "Bras", _detailed_specs([m1, m2], devices))
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": False})
        assert _check(services.compare_setups(v1, v2), "equivalent")


class TestLineageEdges:
    """Cas limites de la relation de lignée (``parent`` / ``placement_inherited_from_parent``)."""

    def test_intermediate_version_changed_placement(self):
        """v1 → v2 (inchangé) → v3 (changé) : v1 et v3 ne sont PAS identical."""
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices = [DeviceFactory(device_model=model) for _ in range(2)]
        v1 = _build(athlete, "Bras", _detailed_specs([m1, m2], devices))
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": True})
        v3 = services.new_version(athlete.user, mark_used(v2), {"placement_unchanged": False})
        # Canaux copiés à chaque étape → alignés : la comparaison retombe dessus.
        assert _check(services.compare_setups(v1, v3), "equivalent")

    def test_sibling_branches_not_direct_lineage(self):
        """Deux enfants de v1 ne forment pas une lignée directe : retour canaux."""
        athlete = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices = [DeviceFactory(device_model=model) for _ in range(2)]
        v1 = _build(athlete, "Bras", _detailed_specs([m1, m2], devices))
        v2 = services.new_version(athlete.user, mark_used(v1), {"placement_unchanged": True})
        v3 = services.new_version(athlete.user, v1, {"placement_unchanged": True})
        assert v2.parent_id == v1.pk and v3.parent_id == v1.pk
        assert _check(services.compare_setups(v2, v3), "equivalent")

    def test_same_name_different_athlete(self):
        """La lignée exige le MÊME sportif : même nom, sportifs différents → canaux."""
        athlete_a = AthleteProfileFactory()
        athlete_b = AthleteProfileFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        model = DeviceModelFactory()
        devices_a = [DeviceFactory(device_model=model) for _ in range(2)]
        devices_b = [DeviceFactory(device_model=model) for _ in range(2)]
        a = _build(athlete_a, "Bras", _detailed_specs([m1, m2], devices_a))
        b = _build(athlete_b, "Bras", _detailed_specs([m1, m2], devices_b))
        assert _check(services.compare_setups(a, b), "equivalent")
