"""Photos de placement (doc 05b) : limites, upload multipart, fichiers orphelins.

- les limites (JPEG/PNG/WebP, 5 Mo max) sont validées sur l'upload EN MÉMOIRE,
  AVANT écriture dans ``default_storage`` (``check_photo_limits``, niveau
  sérialiseur) : type inconnu ou taille dépassée → 400, rien n'est écrit ;
- ``PUT .../channels/`` accepte le multipart à clés indexées plates
  ``channels[i][champ]`` — seul format permettant d'uploader la photo de chaque
  canal (le JSON reste accepté pour les canaux sans photo) ;
- quand des canaux sont supprimés (remplacement, suppression du setup), leur
  fichier est retiré du stockage seulement si plus AUCUN canal ne le référence
  — ``new_version`` copie les canaux en partageant les mêmes fichiers stockés.
"""

from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.client import BOUNDARY, encode_multipart

from apps.accounts.tests.helpers import auth_headers
from apps.athletes.tests.factories import AthleteProfileFactory
from apps.exercises.tests.factories import MuscleFactory
from apps.setups import services
from apps.setups.models import SetupChannel
from apps.setups.serializers import PHOTO_MAX_SIZE_BYTES
from apps.setups.tests.factories import SensorSetupFactory


def _photo(name="placement.jpg", content=b"\xff\xd8\xff\xe0fake-jpeg", content_type="image/jpeg"):
    """Petite photo en mémoire (JPEG par défaut)."""
    return SimpleUploadedFile(name, content, content_type=content_type)


def _channel_entries(muscles, photos=None):
    """Entrées ``set_channels`` minimales ; ``photos`` alignée sur ``muscles``."""
    entries = []
    for index, muscle in enumerate(muscles):
        entry = {
            "device": None,
            "channel_id": index + 1,
            "muscle": muscle,
            "side": "left" if index % 2 == 0 else "right",
        }
        if photos is not None:
            entry["photo"] = photos[index]
        entries.append(entry)
    return entries


def _stored_photo_files():
    """Fichiers présents dans le sous-répertoire des photos de setup."""
    try:
        _, files = default_storage.listdir("setups/photos")
    except OSError:  # répertoire jamais créé (aucune photo écrite en tests)
        return []
    return files


def _multipart_put(client, url, payload, **extra):
    """PUT multipart — le client de test Django n'encode les données dict en
    multipart que pour ``post()`` ; on construit donc le corps soi-même avec
    sa boundary (seule forme possible pour un PUT portant des fichiers)."""
    return client.put(
        url,
        data=encode_multipart(BOUNDARY, payload),
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
        **extra,
    )


class TestPhotoLimits:
    """Type ou taille hors limites → 400, et rien n'est écrit au stockage."""

    def test_wrong_content_type_refused(self, client):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        before = _stored_photo_files()
        response = _multipart_put(
            client,
            f"/api/v1/setups/{setup.pk}/channels/",
            {
                "channels[0][channel_id]": "1",
                "channels[0][muscle]": str(muscle.pk),
                "channels[0][photo]": _photo(name="plan.pdf", content_type="application/pdf"),
            },
            **auth_headers(profile.user),
        )
        assert response.status_code == 400
        assert SetupChannel.objects.count() == 0
        assert _stored_photo_files() == before

    def test_oversized_photo_refused(self, client):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        before = _stored_photo_files()
        too_large = b"\x00" * (PHOTO_MAX_SIZE_BYTES + 1)
        response = _multipart_put(
            client,
            f"/api/v1/setups/{setup.pk}/channels/",
            {
                "channels[0][channel_id]": "1",
                "channels[0][muscle]": str(muscle.pk),
                "channels[0][photo]": _photo(content=too_large),
            },
            **auth_headers(profile.user),
        )
        assert response.status_code == 400
        assert SetupChannel.objects.count() == 0
        assert _stored_photo_files() == before


class TestMultipartChannelsUpload:
    """Le multipart à clés indexées plates converge vers le même contrat JSON."""

    def test_nested_multipart_upload_stores_photo(self, client):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        response = _multipart_put(
            client,
            f"/api/v1/setups/{setup.pk}/channels/",
            {
                "channels[0][channel_id]": "1",
                "channels[0][muscle]": str(muscle.pk),
                "channels[0][side]": "left",
                "channels[0][photo]": _photo(),
            },
            **auth_headers(profile.user),
        )
        assert response.status_code == 200, response.data
        body = response.json()
        assert len(body) == 1
        photo_name = body[0]["photo"]
        assert photo_name.startswith("setups/photos/")
        assert default_storage.exists(photo_name)
        # Une photo est un champ détaillé : le niveau de détail est recalculé.
        setup.refresh_from_db()
        assert setup.detail_level == "detailed"

    def test_multipart_without_photo_stays_simple(self, client):
        profile = AthleteProfileFactory()
        setup = SensorSetupFactory(athlete=profile)
        muscle = MuscleFactory()
        response = _multipart_put(
            client,
            f"/api/v1/setups/{setup.pk}/channels/",
            {
                "channels[0][channel_id]": "1",
                "channels[0][muscle]": str(muscle.pk),
            },
            **auth_headers(profile.user),
        )
        assert response.status_code == 200, response.data
        assert response.json()[0]["photo"] is None
        setup.refresh_from_db()
        assert setup.detail_level == "simple"


class TestOrphanedPhotoCleanup:
    """Les fichiers orphelins sont retirés du stockage (``default_storage``)."""

    def test_replacing_channels_deletes_orphaned_photo(self):
        setup = SensorSetupFactory()
        muscles = [MuscleFactory()]
        services.set_channels(
            setup.athlete.user, setup, _channel_entries(muscles, photos=[_photo()])
        )
        old_name = setup.channels.get().photo.name
        assert default_storage.exists(old_name)
        # Remplacement par une autre photo : l'ancien fichier est orphelin.
        replacement = _photo(name="autre.png", content=b"\x89PNGfake", content_type="image/png")
        services.set_channels(
            setup.athlete.user, setup, _channel_entries(muscles, photos=[replacement])
        )
        assert not default_storage.exists(old_name)
        new_name = setup.channels.get().photo.name
        assert new_name != old_name
        assert default_storage.exists(new_name)

    def test_replacing_channels_without_photo_deletes_file(self):
        setup = SensorSetupFactory()
        services.set_channels(
            setup.athlete.user, setup, _channel_entries([MuscleFactory()], photos=[_photo()])
        )
        old_name = setup.channels.get().photo.name
        services.set_channels(setup.athlete.user, setup, _channel_entries([MuscleFactory()]))
        assert not default_storage.exists(old_name)

    def test_deleting_setup_deletes_its_photos(self):
        setup = SensorSetupFactory()
        services.set_channels(
            setup.athlete.user, setup, _channel_entries([MuscleFactory()], photos=[_photo()])
        )
        name = setup.channels.get().photo.name
        services.delete_setup(setup.athlete.user, setup)
        assert not default_storage.exists(name)

    def test_deleting_newer_version_keeps_photo_shared_with_parent(self):
        """``new_version`` partage les fichiers : supprimer la v2 ne doit pas
        retirer le fichier encore référencé par les canaux de la v1."""
        setup = SensorSetupFactory()
        services.set_channels(
            setup.athlete.user, setup, _channel_entries([MuscleFactory()], photos=[_photo()])
        )
        name = setup.channels.get().photo.name
        v2 = services.new_version(setup.athlete.user, setup, {})
        assert v2.channels.get().photo.name == name  # même fichier stocké
        services.delete_setup(setup.athlete.user, v2)
        assert default_storage.exists(name)  # toujours référencé par la v1
        services.delete_setup(setup.athlete.user, setup)
        assert not default_storage.exists(name)
