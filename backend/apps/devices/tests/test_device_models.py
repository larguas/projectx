"""Tests du catalogue : ``GET /api/v1/device-models/`` (lecture seule).

Le catalogue est visible par tout utilisateur authentifié ; il est géré en
admin et n'admet aucune écriture via l'API (405 sur POST/PUT/PATCH/DELETE).
"""

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import auth_headers, post_json
from apps.devices.tests.factories import DeviceModelFactory


class TestDeviceModelCatalog:
    def test_anonymous_refused(self, client):
        response = client.get("/api/v1/device-models/")
        assert response.status_code == 401

    def test_seed_prototype_v1_present(self, client):
        """Le modèle seedé par la migration de données est présent dans le catalogue."""
        user = UserFactory()
        response = client.get("/api/v1/device-models/", **auth_headers(user))
        assert response.status_code == 200
        results = response.json()["results"]
        prototype = next(d for d in results if d["name"] == "prototype_v1")
        assert prototype["manufacturer"] == "EMG"
        assert prototype["connection_types"] == ["ble"]
        assert prototype["capabilities"]["emg_channels_max"] == 8

    def test_lists_all_models(self, client):
        user = UserFactory()
        model_a = DeviceModelFactory()
        model_b = DeviceModelFactory()
        response = client.get("/api/v1/device-models/", **auth_headers(user))
        ids = {d["id"] for d in response.json()["results"]}
        assert {str(model_a.pk), str(model_b.pk)} <= ids

    def test_filter_by_manufacturer(self, client):
        user = UserFactory()
        model = DeviceModelFactory(manufacturer="Acme")
        DeviceModelFactory(manufacturer="Autre")
        response = client.get("/api/v1/device-models/?manufacturer=Acme", **auth_headers(user))
        assert [d["id"] for d in response.json()["results"]] == [str(model.pk)]

    def test_catalog_is_read_only(self, client):
        user = UserFactory()
        response = post_json(
            client,
            "/api/v1/device-models/",
            {"manufacturer": "X", "name": "y"},
            **auth_headers(user),
        )
        assert response.status_code == 405
