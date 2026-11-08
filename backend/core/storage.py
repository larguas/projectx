"""Abstraction de stockage des signaux bruts (décisions d'architecture n°3 et 5).

Les signaux bruts ne sont JAMAIS stockés en lignes PostgreSQL ni un fichier
par bloc : ils passent par ``RawStore`` en segments. PostgreSQL ne garde que
les métadonnées, chemins et offsets. Les autres fichiers (photos, rapports)
passent par le stockage Django classique (``default_storage``).

L'implémentation (locale d'abord, S3/MinIO ensuite) arrive avec la feature 07.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentRef:
    """Référence d'un segment écrit, à persister en métadonnées PostgreSQL."""

    path: str
    size: int
    sequence_number: int


class RawStore(ABC):
    """Stockage des signaux bruts par segments.

    Identité d'un bloc (idempotence) : ``(session, device, data_type,
    sequence_number)`` — réécrire un bloc déjà reçu doit être sans effet.
    """

    @abstractmethod
    def write_segment(
        self,
        session_id: str,
        device_id: str,
        data_type: str,
        sequence_number: int,
        payload: bytes,
    ) -> SegmentRef:
        """Écrit un segment (sans doublon si déjà reçu) et retourne sa référence."""

    @abstractmethod
    def read_segment(self, ref: SegmentRef) -> bytes:
        """Lit le contenu d'un segment."""

    @abstractmethod
    def exists(self, session_id: str, device_id: str, data_type: str, sequence_number: int) -> bool:
        """Vérifie si un bloc a déjà été reçu (idempotence)."""


class LocalRawStore(RawStore):
    """Implémentation locale sur disque — implémentée en feature 07."""

    def write_segment(
        self,
        session_id: str,
        device_id: str,
        data_type: str,
        sequence_number: int,
        payload: bytes,
    ) -> SegmentRef:
        raise NotImplementedError("LocalRawStore sera implémenté en feature 07")

    def read_segment(self, ref: SegmentRef) -> bytes:
        raise NotImplementedError("LocalRawStore sera implémenté en feature 07")

    def exists(self, session_id: str, device_id: str, data_type: str, sequence_number: int) -> bool:
        raise NotImplementedError("LocalRawStore sera implémenté en feature 07")
