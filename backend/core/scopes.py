"""Scopes d'accès centralisés (décision d'architecture n°8).

Les scopes sont définis UNIQUEMENT dans ce module, jamais en chaînes libres
dans le code. Toute validation d'un grant passe par ``validate_scopes`` :
un grant peut combiner plusieurs scopes, mais tout scope inconnu est refusé.

Exemple::

    from core import scopes

    scopes.validate_scopes(["sessions:read", "reports:read"])  # OK
    scopes.validate_scopes(["sessions:read", "banane:read"])   # ValueError
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
    """Tous les scopes enregistrés (référencés par le schéma OpenAPI)."""
    return tuple(_REGISTRY.values())


# --- Scopes de la plateforme (feature 03) --------------------------------------

SESSIONS_READ = register_scope("sessions:read", "Lecture des séances d'entraînement.")
SESSIONS_WRITE = register_scope("sessions:write", "Création / modification de séances.")
ANALYTICS_READ = register_scope("analytics:read", "Lecture des résultats d'analyse.")
REPORTS_READ = register_scope("reports:read", "Lecture des rapports.")
DEVICES_READ = register_scope("devices:read", "Lecture des capteurs liés au sportif.")
SETUPS_READ = register_scope("setups:read", "Lecture des setups de placement.")
SETUPS_WRITE = register_scope("setups:write", "Création / modification de setups.")


def is_known_scope(name: str) -> bool:
    """Le scope est-il enregistré ?"""
    return name in _REGISTRY


def validate_scopes(scopes: object) -> list[str]:
    """Valide une liste de scopes ; lève ``ValueError`` sinon.

    - la valeur doit être un iterable de chaînes (liste/tuple) ;
    - elle ne doit pas être vide ;
    - chaque scope doit être enregistré dans ce module (les inconnus sont refusés) ;
    - les doublons sont retirés (l'ordre d'apparition est conservé).

    Retourne la liste propre, prête à être stockée sur un ``AccessGrant``.
    """
    if isinstance(scopes, str) or not hasattr(scopes, "__iter__"):
        raise ValueError("Les scopes doivent être fournis sous forme de liste.")
    names = list(scopes)
    if not names:
        raise ValueError("Au moins un scope est obligatoire.")
    clean: list[str] = []
    for name in names:
        if not isinstance(name, str):
            raise ValueError(f"Scope invalide : {name!r} (chaîne attendue).")
        try:
            get_scope(name)
        except KeyError:  # scope inconnu refusé (code stable ValueError)
            raise ValueError(f"Scope inconnu : {name!r}") from None
        if name not in clean:
            clean.append(name)
    return clean
