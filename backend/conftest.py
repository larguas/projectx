"""Protection des données seedées de la base de tests partagée (``--reuse-db``).

Les trois migrations de données (devices, exercises, setups) peuplent la base de
tests une seule fois, à sa création. Les tests marqués ``django_db(transaction=True)``
tournent dans un vrai ``TransactionTestCase`` : Django *flush* l'intégralité de la
base au teardown, ce qui efface ces données seedées et casse tous les tests
non-transactionnels suivants de la session (ils s'appuient sur les catalogues
globaux — exercices, modèles de capteurs, guides de pose).

Après chaque test transactionnel, on réapplique donc les trois migrations de
seed, idempotentes (``get_or_create``). Le flush se fait dans un finaliseur de
fixture, après lequel pytest-django a re-bloqué l'accès à la base : le hook
wrapper sur ``pytest_runtest_teardown`` est exécuté *après* tous les finaliseurs,
et on y réactive temporairement l'accès réel via l'instance globale de
``DjangoDbBlocker`` (seule elle détient la référence à l'implémentation réelle
de ``ensure_connection``, capturée avant le premier blocage).
"""

import contextlib
from collections.abc import Iterator

import pytest

#: Migrations de données seedées, idempotentes (``get_or_create``).
_SEED_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("devices", "0002_seed_prototype_v1"),
    ("exercises", "0003_seed_library_v1"),
    ("setups", "0003_seed_placement_guides"),
)


def _global_db_blocker(config):
    """L'instance globale de ``DjangoDbBlocker``, ou ``None`` si non configurée."""
    from pytest_django.plugin import DjangoDbBlocker, blocking_manager_key

    if blocking_manager_key not in config.stash:
        return None
    blocker = config.stash[blocking_manager_key]
    assert isinstance(blocker, DjangoDbBlocker)
    return blocker


@contextlib.contextmanager
def _unblocked_db(config) -> Iterator[None]:
    """Restaure temporairement l'accès réel à la base en dehors d'un test."""
    blocker = _global_db_blocker(config)
    if blocker is None:  # Django non configuré : rien à faire.
        yield
        return
    with blocker.unblock():
        yield


def _reapply_seed_migrations() -> None:
    """Ré-exécute les trois migrations de seed sur la base de tests courante."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    # Sans effacer l'entrée ``django_migrations``, le migrateur considérerait
    # les migrations comme déjà appliquées et ne les ré-exécuterait pas.
    with connection.cursor() as cursor:
        for app_label, name in _SEED_MIGRATIONS:
            cursor.execute(
                "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                [app_label, name],
            )

    executor = MigrationExecutor(connection)
    for app_label, name in _SEED_MIGRATIONS:
        key = (app_label, name)
        state = executor.loader.project_state(key, at_end=False)
        migration = executor.loader.graph.nodes[key]
        executor.apply_migration(state, migration)


def _is_transactional_db_test(item) -> bool:
    """Vrai si le test tourne dans un ``TransactionTestCase`` (flush au teardown)."""
    from pytest_django.fixtures import validate_django_db

    marker = item.get_closest_marker("django_db")
    if marker is None:
        return False
    transaction, reset_sequences, _databases, _serialized_rollback, _available_apps = (
        validate_django_db(marker)
    )
    # ``reset_sequences`` impose aussi un TransactionTestCase → flush au teardown.
    return bool(transaction or reset_sequences)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item, nextitem):  # noqa: ARG001
    """Ré-seed la base après chaque test qui l'a flushée (transactionnel)."""
    try:
        yield
    finally:
        if _is_transactional_db_test(item):
            with _unblocked_db(item.config):
                _reapply_seed_migrations()
