"""Versionnement et immutabilité des setups (couche services).

Règles couvertes :
- un setup est modifiable librement TANT QU'AUCUNE SÉANCE ne l'utilise
  (création, update, remplacement des canaux, suppression) ;
- le nom d'un setup est unique par sportif (``name_taken``) ;
- une fois « utilisé » (marqueur ``used_at``, point d'extension unique de la
  feature 06), toute mutation est refusée en SERVICE (``setup_frozen``) ET en
  MODÈLE (``save()`` -> ``assert_editable``) — la spec exige cette double
  vérification ; ``new_version`` reste le seul chemin d'évolution ;
- ``new_version`` crée la version n+1 avec lignée ``parent``, copie les canaux
  et bascule ``is_current`` par mise à jour en base ciblée (jamais de
  ``save()`` sur la source figée) ;
- suppression refusée si utilisé / calibrations / versions enfants.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.athletes.tests.factories import AthleteProfileFactory
from apps.setups import services
from apps.setups.models import SensorSetup, SetupChannel
from apps.setups.tests.factories import (
    CalibrationFactory,
    SensorSetupFactory,
    SetupChannelFactory,
    mark_used,
)


def _channel_entries(muscles):
    """Entrées ``set_channels`` minimales (mode simple : muscle + côté)."""
    return [
        {
            "device": None,
            "channel_id": index + 1,
            "muscle": muscle,
            "side": "left" if index % 2 == 0 else "right",
        }
        for index, muscle in enumerate(muscles)
    ]


class TestCreateSetup:
    def test_creates_version_1_for_athlete(self):
        setup = SensorSetupFactory()  # référence des champs attendus
        athlete = setup.athlete
        created = services.create_setup(
            user=athlete.user, data={"athlete": athlete, "name": "Jambes", "notes": ""}
        )
        assert created.version == 1
        assert created.is_current is True
        assert created.detail_level == SensorSetup.DetailLevel.SIMPLE
        assert created.created_by_id == athlete.user_id

    def test_name_taken_refused(self):
        existing = SensorSetupFactory(name="Bras")
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.create_setup(
                user=existing.athlete.user,
                data={"athlete": existing.athlete, "name": "Bras", "notes": ""},
            )
        assert excinfo.value.code == "name_taken"

    def test_same_name_other_athlete_allowed(self):
        setup = SensorSetupFactory(name="Bras")
        other = AthleteProfileFactory()
        created = services.create_setup(
            user=other.user, data={"athlete": other, "name": "Bras", "notes": ""}
        )
        assert created.pk != setup.pk


class TestFreeEditingBeforeUse:
    def test_update_name_and_notes(self):
        setup = SensorSetupFactory()
        updated = services.update_setup(
            setup.athlete.user, setup, {"name": "Bras v2", "notes": "peau préparée"}
        )
        assert updated.name == "Bras v2"
        assert updated.notes == "peau préparée"

    def test_set_channels_replaces_atomically(self):
        from apps.exercises.tests.factories import MuscleFactory

        setup = SensorSetupFactory()
        muscles = [MuscleFactory(), MuscleFactory()]
        channels = services.set_channels(setup.athlete.user, setup, _channel_entries(muscles))
        assert [c.channel_id for c in channels] == [1, 2]
        # Remplacement complet : l'ancienne liste disparaît.
        muscles_b = [MuscleFactory()]
        channels = services.set_channels(setup.athlete.user, setup, _channel_entries(muscles_b))
        assert setup.channels.count() == 1
        assert channels[0].muscle_id == muscles_b[0].pk

    def test_detail_level_forced_simple_without_detailed_fields(self):
        from apps.exercises.tests.factories import MuscleFactory

        setup = SensorSetupFactory(detail_level=SensorSetup.DetailLevel.DETAILED)
        services.set_channels(setup.athlete.user, setup, _channel_entries([MuscleFactory()]))
        setup.refresh_from_db()
        assert setup.detail_level == SensorSetup.DetailLevel.SIMPLE

    def test_detail_level_detailed_when_a_channel_has_detailed_field(self):
        from apps.exercises.tests.factories import MuscleFactory

        setup = SensorSetupFactory()
        entries = _channel_entries([MuscleFactory()])
        entries[0]["position_note"] = "1/3 bas du ventre du muscle"
        services.set_channels(setup.athlete.user, setup, entries)
        setup.refresh_from_db()
        assert setup.detail_level == SensorSetup.DetailLevel.DETAILED


class TestImmutabilityMechanism:
    """Le mécanisme d'immutabilité (marqueur ``used_at``), pas les séances.

    La feature 06 posera ce marqueur à la première utilisation ; ici on le
    pose via ``mark_used`` (mise à jour ciblée, comme le fera la feature 06)
    pour tester que TOUTES les mutations sont refusées — service ET modèle.
    """

    def test_update_refused_when_used(self):
        setup = mark_used(SensorSetupFactory())
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.update_setup(setup.athlete.user, setup, {"name": "Modifié"})
        assert excinfo.value.code == "setup_frozen"

    def test_set_channels_refused_when_used(self):
        from apps.exercises.tests.factories import MuscleFactory

        setup = mark_used(SensorSetupFactory())
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.set_channels(setup.athlete.user, setup, _channel_entries([MuscleFactory()]))
        assert excinfo.value.code == "setup_frozen"

    def test_delete_refused_when_used(self):
        setup = mark_used(SensorSetupFactory())
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.delete_setup(setup.athlete.user, setup)
        assert excinfo.value.code == "setup_frozen"

    def test_model_save_refused_when_used(self):
        """Niveau MODÈLE : ``save()`` appelle ``assert_editable``."""
        setup = mark_used(SensorSetupFactory())
        setup.notes = "tentative de contournement du service"
        with pytest.raises(ValidationError):
            setup.save()

    def test_state_flip_never_goes_through_save(self):
        """Le basculement ``used_at`` passe par une mise à jour ciblée.

        C'est ce qui rend l'immutabilité cohérente : un setup figé refuse
        ``save()``, donc tout changement d'état doit éviter ce chemin.
        """
        setup = mark_used(SensorSetupFactory())
        assert setup.used_at is not None
        assert setup.is_used is True


class TestNewVersion:
    def test_creates_n_plus_1_with_parent_lineage(self):
        source = mark_used(SensorSetupFactory(name="Bras"))
        new = services.new_version(source.athlete.user, source, {"placement_unchanged": False})
        assert new.version == 2
        assert new.parent_id == source.pk
        assert new.is_current is True
        source.refresh_from_db()
        assert source.is_current is False

    def test_source_never_saved_when_flipping_is_current(self):
        """La version figée n'est jamais sauvegardée (``updated_at`` intact)."""
        source = mark_used(SensorSetupFactory())
        updated_before = source.updated_at
        services.new_version(source.athlete.user, source, {})
        source.refresh_from_db()
        assert source.updated_at == updated_before

    def test_copies_channels_completely(self):
        from apps.exercises.tests.factories import MuscleFactory

        source = SensorSetupFactory()
        m1, m2 = MuscleFactory(), MuscleFactory()
        services.set_channels(source.athlete.user, source, _channel_entries([m1, m2]))
        source = mark_used(source)
        new = services.new_version(source.athlete.user, source, {})
        old_by_key = {(c.device_id, c.channel_id): c for c in source.channels.all()}
        for new_channel in new.channels.all():
            old_channel = old_by_key[(new_channel.device_id, new_channel.channel_id)]
            assert new_channel.muscle_id == old_channel.muscle_id
            assert new_channel.side == old_channel.side
            assert new_channel.position_note == old_channel.position_note
            assert (
                new_channel.inter_electrode_distance_mm == old_channel.inter_electrode_distance_mm
            )

    def test_new_version_still_works_on_used_setup(self):
        """C'est TOUT L'INTÉRÊT de ``new_version`` sur un setup figé."""
        source = mark_used(SensorSetupFactory())
        new = services.new_version(source.athlete.user, source, {})
        assert new.is_used is False
        # La copie est librement modifiable tant qu'aucune séance ne l'utilise.
        services.update_setup(new.athlete.user, new, {"notes": "modifié sur la copie"})

    def test_version_number_follows_max_of_lineage(self):
        source = SensorSetupFactory(name="Bras")
        v2 = services.new_version(source.athlete.user, source, {})
        v3 = services.new_version(source.athlete.user, v2, {})
        assert (v2.version, v3.version) == (2, 3)
        assert v3.parent_id == v2.pk


class TestDeleteSetup:
    def test_delete_ok_when_unused(self):
        setup = SensorSetupFactory()
        SetupChannelFactory(setup=setup)
        services.delete_setup(setup.athlete.user, setup)
        assert not SensorSetup.objects.filter(pk=setup.pk).exists()

    def test_refused_with_child_versions(self):
        source = SensorSetupFactory(name="Bras")
        services.new_version(source.athlete.user, source, {})
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.delete_setup(source.athlete.user, source)
        assert excinfo.value.code == "has_newer_version"

    def test_refused_with_calibrations(self):
        setup = SensorSetupFactory()
        CalibrationFactory(setup=setup)
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.delete_setup(setup.athlete.user, setup)
        assert excinfo.value.code == "has_calibrations"

    def test_delete_cascades_channels(self):
        setup = SensorSetupFactory()
        SetupChannelFactory(setup=setup)
        services.delete_setup(setup.athlete.user, setup)
        assert not SetupChannel.objects.filter(setup_id=setup.pk).exists()


class TestServiceAccessControl:
    def test_write_requires_access_to_athlete(self):
        from apps.accounts.tests.factories import UserFactory

        setup = SensorSetupFactory()
        stranger = UserFactory()
        with pytest.raises(services.SetupsServiceError) as excinfo:
            services.update_setup(stranger, setup, {"name": "Intrus"})
        assert excinfo.value.code == "forbidden"

    def test_owner_always_allowed(self):
        setup = SensorSetupFactory()
        updated = services.update_setup(setup.athlete.user, setup, {"notes": "ok"})
        assert updated.notes == "ok"
