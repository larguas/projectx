"""Décodage de paquets et sonde de compteurs — fonctions pures, sans I/O.

Le format de paquet réel du capteur est inconnu au démarrage du spike
(question 3 du doc). Deux outils, tous deux purs et testables :

- ``read_int`` / ``FieldSpec`` : extraction explicite d'un entier sur des
  offsets connus (à renseigner par l'utilisateur une fois le format observé).
- ``probe_counters`` : balayage heuristique des positions de paquet qui
  ressemblent à un compteur croissant, pour *aider* à identifier le numéro
  de séquence du capteur (question 7) sans inventer de valeur.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

_ENDIAN_PREFIX = {"little": "<", "big": ">"}
_SIZE_FORMAT = {1: "B", 2: "H", 4: "I"}


@dataclass(frozen=True)
class FieldSpec:
    """Position d'un entier dans le paquet (offset en octets, taille, endianness)."""

    offset: int
    size_bytes: int = 4
    endian: str = "little"

    def read(self, payload: bytes) -> int | None:
        """Valeur entière du champ, ou ``None`` si le paquet est trop court."""
        if self.size_bytes not in _SIZE_FORMAT:
            raise ValueError(f"taille non supportée : {self.size_bytes}")
        if len(payload) < self.offset + self.size_bytes:
            return None
        fmt = _ENDIAN_PREFIX[self.endian] + _SIZE_FORMAT[self.size_bytes]
        return struct.unpack_from(fmt, payload, self.offset)[0]


def read_int(payload: bytes, offset: int, size_bytes: int, endian: str = "little") -> int | None:
    """Lecture d'un entier non signé sur ``payload`` (alias pratique de FieldSpec)."""
    return FieldSpec(offset, size_bytes, endian).read(payload)


@dataclass(frozen=True)
class CounterCandidate:
    """Position candidate pour un compteur croissant dans le flux."""

    offset: int
    size_bytes: int
    endian: str
    n_pairs: int
    n_increments: int
    start_value: int | None
    end_value: int | None
    fraction_increasing: float

    @property
    def label(self) -> str:
        return f"offset={self.offset} size={self.size_bytes}B {self.endian}"


def probe_counters(
    payloads: list[bytes],
    max_size: int = 4,
    jump_threshold: int = 1000,
    min_packets: int = 5,
    min_fraction: float = 0.9,
) -> list[CounterCandidate]:
    """Sonde les positions qui ressemblent à un compteur croissant paquet après paquet.

    Une position « candidate » est une offset où, pour au moins ``min_fraction``
    des paires consécutives, la valeur augmente d'un pas plausible (1..jump_threshold),
    en tolérant le retour à zéro du compteur (wrap). Les candidats sont triés par
    qualité décroissante. Fonction pure : aucune interprétation n'est imposée au flux.
    """
    if len(payloads) < min_packets:
        return []

    max_len = max(len(p) for p in payloads)
    candidates: list[CounterCandidate] = []

    for size in (1, 2, 4):
        if size > max_size:
            continue
        modulus = 1 << (8 * size)
        # Dernier offset valide : offset + size <= max_len (les deux bornes incluses).
        for offset in range(max(0, max_len - size + 1)):
            start_value: int | None = None
            prev: int | None = None
            n_pairs = 0
            n_increments = 0
            end_value: int | None = None

            for payload in payloads:
                value = read_int(payload, offset, size)
                if value is None:
                    continue
                if start_value is None:
                    start_value = value
                end_value = value
                if prev is not None:
                    n_pairs += 1
                    # En arithmétique modulaire, une augmentation « normale » et un
                    # wrap (retour à zéro après la valeur max) donnent tous deux un
                    # petit delta positif ; une vraie diminution donne un grand delta.
                    if 1 <= (value - prev) % modulus <= jump_threshold:
                        n_increments += 1
                prev = value

            if start_value is None or n_pairs < min_packets - 1:
                continue
            fraction = n_increments / n_pairs
            if fraction >= min_fraction:
                candidates.append(
                    CounterCandidate(
                        offset=offset,
                        size_bytes=size,
                        endian="little",
                        n_pairs=n_pairs,
                        n_increments=n_increments,
                        start_value=start_value,
                        end_value=end_value,
                        fraction_increasing=fraction,
                    )
                )

    candidates.sort(key=lambda c: (-c.fraction_increasing, c.size_bytes, c.offset))
    return candidates[:10]
