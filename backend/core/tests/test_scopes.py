"""Tests des scopes centralisés (``core.scopes``).

Les scopes sont la source de vérité de toutes les autorisations : tout scope
inconnu doit être refusé, où qu'il soit validé.
"""

import pytest

from core import scopes


class TestScopeRegistry:
    def test_feature03_scopes_registered(self):
        names = {scope.name for scope in scopes.all_scopes()}
        assert names == {
            "sessions:read",
            "sessions:write",
            "analytics:read",
            "reports:read",
            "devices:read",
            "setups:read",
            "setups:write",
        }

    def test_is_known_scope(self):
        assert scopes.is_known_scope("sessions:read") is True
        assert scopes.is_known_scope("bogus:scope") is False

    def test_get_scope_returns_description(self):
        scope = scopes.get_scope("analytics:read")
        assert scope.name == "analytics:read"
        assert scope.description

    def test_get_scope_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            scopes.get_scope("bogus:scope")

    def test_register_duplicate_raises(self):
        with pytest.raises(ValueError):
            scopes.register_scope("sessions:read")


class TestValidateScopes:
    def test_valid_list(self):
        assert scopes.validate_scopes(["sessions:read", "reports:read"]) == [
            "sessions:read",
            "reports:read",
        ]

    def test_single_scope(self):
        assert scopes.validate_scopes(["devices:read"]) == ["devices:read"]

    def test_empty_list_refused(self):
        with pytest.raises(ValueError, match="Au moins un scope"):
            scopes.validate_scopes([])

    def test_unknown_scope_refused(self):
        with pytest.raises(ValueError, match="Scope inconnu"):
            scopes.validate_scopes(["sessions:read", "banane:read"])

    def test_all_unknown_refused(self):
        with pytest.raises(ValueError, match="Scope inconnu"):
            scopes.validate_scopes(["nope:write"])

    def test_duplicates_removed_order_preserved(self):
        assert scopes.validate_scopes(["reports:read", "sessions:read", "reports:read"]) == [
            "reports:read",
            "sessions:read",
        ]

    def test_string_is_not_a_list(self):
        # Une chaîne est itérable : elle doit être refusée explicitement.
        with pytest.raises(ValueError, match="liste"):
            scopes.validate_scopes("sessions:read")

    def test_non_iterable_refused(self):
        with pytest.raises(ValueError, match="liste"):
            scopes.validate_scopes(42)

    def test_non_string_item_refused(self):
        with pytest.raises(ValueError, match="chaîne attendue"):
            scopes.validate_scopes(["sessions:read", 7])
