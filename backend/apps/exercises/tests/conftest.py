"""Configuration des tests de la feature 05 : accès BDD actif par défaut."""

import pytest
from django.core.cache import cache


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.django_db)


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Évite la contamination entre tests du cache de throttling (locmem)."""
    cache.clear()
    yield
    cache.clear()
