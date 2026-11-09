"""Lecture du capteur : horodatage hôte de chaque enregistrement, sortie brute JSONL.

Deux transports, selon la connexion réelle du capteur (question 1 du spike) :
- BLE via ``bleak`` (notifications GATT) — asynchrone ;
- série via ``pyserial`` (/dev/ttyUSB*, /dev/ttyACM*) — synchrone.

Chaque paquet reçu est horodaté CÔTÉ HÔTE avant tout autre traitement :
- ``recv_ts_mono`` : ``time.monotonic()`` au moment de la réception
  (inter-arrivées, jitter) ;
- ``recv_ts_utc``  : horloge murale UTC (corrélation, dérive vs horloge capteur).

Le fichier brut est un JSONL lisible a posteriori (header / records / footer),
analysable par ``analyze_capture.py`` sans ré-enregistrement.

Aucune valeur n'est inventée : si le capteur n'expose pas de numéro de séquence
ou de timestamp, les champs correspondants sont ``null`` dans le fichier.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spike.parse import FieldSpec

CAPTURE_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """Horodatage UTC ISO-8601 (millisecondes), ex. ``2026-11-09T14:30:00.123Z``."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class CaptureRecord:
    """Un paquet reçu, horodaté côté hôte, payload brut conservé tel quel."""

    recv_ts_mono: float
    recv_ts_utc: str
    payload: bytes
    seq: int | None = None
    sensor_ts_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "record",
            "recv_ts_mono": self.recv_ts_mono,
            "recv_ts_utc": self.recv_ts_utc,
            "n_bytes": len(self.payload),
            "payload_hex": self.payload.hex(),
            "seq": self.seq,
            "sensor_ts_ms": self.sensor_ts_ms,
        }


@dataclass
class ExtractionConfig:
    """Extraction explicite de champs du paquet (offsets à renseigner après Q3).

    Tant que le format réel n'est pas connu, laisser les offsets à ``None`` :
    les champs seront ``null`` dans la capture, et ``analyze_capture.py --probe``
    aidera à les identifier.
    """

    seq_offset: int | None = None
    seq_size: int = 4
    seq_endian: str = "little"
    sensor_ts_offset: int | None = None
    sensor_ts_size: int = 4
    sensor_ts_endian: str = "little"

    def extract(self, payload: bytes) -> tuple[int | None, float | None]:
        seq: int | None = None
        sensor_ts_ms: float | None = None
        if self.seq_offset is not None:
            spec = FieldSpec(self.seq_offset, self.seq_size, self.seq_endian)
            seq = spec.read(payload)
        if self.sensor_ts_offset is not None:
            spec = FieldSpec(self.sensor_ts_offset, self.sensor_ts_size, self.sensor_ts_endian)
            value = spec.read(payload)
            sensor_ts_ms = float(value) if value is not None else None
        return seq, sensor_ts_ms


def make_record(
    payload: bytes, extraction: ExtractionConfig | None = None
) -> CaptureRecord:
    """Construit un enregistrement horodaté à l'instant T (à appeler à la réception)."""
    seq = sensor_ts_ms = None
    if extraction is not None:
        seq, sensor_ts_ms = extraction.extract(payload)
    return CaptureRecord(
        recv_ts_mono=time.monotonic(),
        recv_ts_utc=utc_now_iso(),
        payload=payload,
        seq=seq,
        sensor_ts_ms=sensor_ts_ms,
    )


class JsonlCaptureWriter:
    """Écriture JSONL (header + records + footer), sûre multithread.

    Format :
    - ligne 1 : ``{"type": "header", ...}`` (machine, transport, device, options) ;
    - lignes suivantes : ``{"type": "record", ...}`` un par paquet ;
    - dernière ligne : ``{"type": "footer", ...}`` (durée, compteurs).
    """

    def __init__(self, path: Path, header: dict[str, Any]) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._n_records = 0
        self._bytes_total = 0
        self._started_mono = time.monotonic()
        self._fh = path.open("w", encoding="utf-8")
        header = {"type": "header", "schema_version": CAPTURE_SCHEMA_VERSION, **header}
        self._fh.write(json.dumps(header, ensure_ascii=False) + "\n")
        self._fh.flush()

    @property
    def n_records(self) -> int:
        return self._n_records

    @property
    def bytes_total(self) -> int:
        return self._bytes_total

    def record(self, rec: CaptureRecord) -> None:
        with self._lock:
            self._fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            self._n_records += 1
            self._bytes_total += len(rec.payload)
            if self._n_records % 200 == 0:  # flush périodique : limite la perte en cas de crash
                self._fh.flush()

    def close(self, note: str = "") -> dict[str, Any]:
        with self._lock:
            duration_s = time.monotonic() - self._started_mono
            footer: dict[str, Any] = {
                "type": "footer",
                "ended_at_utc": utc_now_iso(),
                "duration_s": round(duration_s, 3),
                "n_records": self._n_records,
                "payload_bytes_total": self._bytes_total,
            }
            if note:
                footer["note"] = note
            self._fh.write(json.dumps(footer, ensure_ascii=False) + "\n")
            self._fh.flush()
            self._fh.close()
            return footer


class BleCaptureSession:
    """Lecture BLE : connecte, découvre le caractère notifiable, callback par paquet.

    Si ``char_uuid`` n'est pas fourni, le premier caractère avec la propriété
    ``notify``/``indicate`` est retenu (heuristique de spike — à confirmer une
    fois le service GATT réel observé) ; tous les candidats sont listés sur stderr.
    """

    def __init__(
        self,
        on_packet: Callable[[bytes], None],
        address: str | None = None,
        name_substr: str | None = None,
        service_uuid: str | None = None,
        char_uuid: str | None = None,
        scan_timeout: float = 10.0,
    ) -> None:
        self.on_packet = on_packet
        self.address = address
        self.name_substr = name_substr
        self.service_uuid = service_uuid
        self.char_uuid = char_uuid
        self.scan_timeout = scan_timeout
        self._client: Any = None
        self.device_info: dict[str, Any] = {}

    async def _resolve_address(self) -> str:
        if self.address:
            return self.address
        from bleak import BleakScanner

        if not self.name_substr:
            raise RuntimeError("BLE : --address ou --name requis (aucun capteur présélectionné)")
        device = await BleakScanner.find_device_by_name(self.name_substr, timeout=self.scan_timeout)
        if device is None:
            raise RuntimeError(f"BLE : aucun appareil nommé ~ « {self.name_substr } » vu pendant le scan")
        return device.address

    def _pick_characteristic(self, client: Any) -> tuple[str, str]:
        """Retourne (service_uuid, char_uuid) ; heuristique si non précisé."""
        services = client.services
        candidates: list[tuple[str, str]] = []
        for service in services:
            if self.service_uuid and service.uuid.lower().replace("-", "") != (
                self.service_uuid.lower().replace("-", "")
            ):
                continue
            for char in service.characteristics:
                props = set(char.properties)
                if "notify" in props or "indicate" in props:
                    candidates.append((service.uuid, char.uuid))

        if not candidates:
            raise RuntimeError("BLE : aucun caractère notifiable trouvé dans le GATT")

        if self.char_uuid:
            for service_uuid, c_uuid in candidates:
                if c_uuid.lower().replace("-", "") == self.char_uuid.lower().replace("-", ""):
                    return service_uuid, c_uuid
            raise RuntimeError(f"BLE : caractère {self.char_uuid} introuvable ou non notifiable")

        import sys

        print(
            "[ble] caractères notifiables candidats :",
            file=sys.stderr,
        )
        for s_uuid, c_uuid in candidates:
            print(f"  service={s_uuid} char={c_uuid}", file=sys.stderr)
        chosen = candidates[0]
        print(f"[ble] choix automatique (heuristique spike) : {chosen[1]}", file=sys.stderr)
        return chosen

    async def start(self) -> dict[str, Any]:
        from bleak import BleakClient

        address = await self._resolve_address()
        client = BleakClient(address)
        await client.connect()
        self._client = client
        service_uuid, char_uuid = self._pick_characteristic(client)
        self.device_info = {
            "address": address,
            "name": client.pairwise_id or "",
            "service_uuid": service_uuid,
            "char_uuid": char_uuid,
        }

        def _on_notify(_characteristic: Any, data: bytearray) -> None:
            # Signature du callback : (BLECharacteristic, bytearray) en bleak récent.
            self.on_packet(bytes(data))

        await client.start_notify(char_uuid, _on_notify)
        return self.device_info

    async def stop(self) -> None:
        if self._client is not None and self._client.is_connected:
            try:
                await self._client.disconnect()
            finally:
                self._client = None


class SerialCaptureSession:
    """Lecture série : boucle de lecture bloquante, un enregistrement par chunk (ou par ligne)."""

    def __init__(
        self,
        on_packet: Callable[[bytes], None],
        port: str,
        baudrate: int = 115200,
        line_mode: bool = False,
    ) -> None:
        self.on_packet = on_packet
        self.port = port
        self.baudrate = baudrate
        self.line_mode = line_mode
        self._ser: Any = None
        self.device_info: dict[str, Any] = {"port": port, "baudrate": baudrate, "line_mode": line_mode}

    def start(self) -> dict[str, Any]:
        import serial

        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.25)
        return self.device_info

    def run_until(self, stop_event: threading.Event) -> None:
        assert self._ser is not None, "appeler start() d'abord"
        buffer = b""
        while not stop_event.is_set():
            chunk = self._ser.read(4096)
            if not chunk:
                continue
            if self.line_mode:
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.rstrip(b"\r")
                    if line:
                        self.on_packet(line)
            else:
                self.on_packet(chunk)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None


def load_capture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    """Relit un fichier de capture JSONL. Retourne (header, records, footer)."""
    header: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    footer: dict[str, Any] | None = None
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            kind = obj.get("type")
            if kind == "header":
                header = obj
            elif kind == "record":
                records.append(obj)
            elif kind == "footer":
                footer = obj
    return header, records, footer


async def run_ble_capture(
    writer: JsonlCaptureWriter,
    extraction: ExtractionConfig | None,
    duration_s: float,
    session: BleCaptureSession,
) -> None:
    """Boucle BLE : capture pendant ``duration_s`` (ou jusqu'à Ctrl-C)."""

    def on_packet(payload: bytes) -> None:
        writer.record(make_record(payload, extraction))

    session.on_packet = on_packet
    stop = asyncio.Event()

    async def _watchdog() -> None:
        await asyncio.sleep(duration_s)
        stop.set()

    watchdog = asyncio.create_task(_watchdog())
    try:
        await session.start()
        await stop.wait()
    finally:
        watchdog.cancel()
        await session.stop()


def run_serial_capture(
    writer: JsonlCaptureWriter,
    extraction: ExtractionConfig | None,
    duration_s: float,
    session: SerialCaptureSession,
) -> None:
    """Boucle série : capture pendant ``duration_s`` (ou jusqu'à Ctrl-C)."""
    stop = threading.Event()

    def on_packet(payload: bytes) -> None:
        writer.record(make_record(payload, extraction))

    session.on_packet = on_packet
    try:
        session.start()
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline and not stop.is_set():
            session.run_until(stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        session.close()
