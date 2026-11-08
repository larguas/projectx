"""Scopes d'accès centralisés (décision d'architecture n°8).

Les scopes sont définis UNIQUEMENT dans ce module, jamais en chaînes libres
dans le code. La liste est remplie par la feature 03 ; le mécanisme
d'enregistrement existe dès le socle.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
    name: str
    description: str = ""


_REGISTRY: dict[str, Scope] = {}


def register_scope(name: str, description: str = "") -> Scope:
    """Enregistre un scope ; lève ``ValueError`` si le nom est déjà pris."""
    if name in _REGISTRY:
        raise ValueError(f"Scope déjà enregistré : {name!r}")
    scope = Scope(name=name, description=description)
    _REGISTRY[name] = scope
    return scope


def get_scope(name: str) -> Scope:
    """Retourne le scope enregistré ou lève ``KeyError``."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Scope inconnu : {name!r}") from None


def all_scopes() -> tuple[Scope, ...]:
    """Tous les scopes enregistrés (liste vide tant que la feature 03 n'est pas faite)."""
    return tuple(_REGISTRY.values())
