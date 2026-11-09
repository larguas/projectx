#!/usr/bin/env python3
"""Lecture du capteur EMG/IMU réel — point d'entrée CLI du spike 06b.

Étapes recommandées :
1. ``uv run detect_device.py`` → identifier la connexion réelle (question 1) ;
2. lancer cette capture avec le bon transport et une durée suffisante
   (≥ 600 s recommandé pour la dérive d'horloge sur 10 min) ;
3. ``uv run analyze_capture.py --input <fichier.jsonl>`` → métriques.

Le fichier JSONL de sortie est horodaté côté hôte (monotone + UTC) et lisible
a posteriori : aucun ré-enregistrement n'est nécessaire pour re-analyser.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spike.capture import (
    BleCaptureSession,
    ExtractionConfig,
    JsonlCaptureWriter,
    SerialCaptureSession,
    run_ble_capture,
    run_serial_capture,
)


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la capture."""
    parser = argparse.ArgumentParser(
        description="Lecture du capteur EMG/IMU (spike 06b) — capture brute JSONL horodatée côté hôte.",
    )
    parser.add_argument(
        "--transport",
        choices=["auto", "ble", "serial"],
        default="auto",
        help="Transport à utiliser (défaut : auto = détection best-effort)",
    )
    # --- BLE -------------------------------------------------------------
    parser.add_argument("--address", help="Adresse MAC/UUID BLE du capteur")
    parser.add_argument("--name", help="Sous-chaîne du nom BLE du capteur (scan)")
    parser.add_argument("--service-uuid", dest="service_uuid", help="UUID du service GATT (optionnel)")
    parser.add_argument("--char-uuid", dest="char_uuid", help="UUID du caractère notifiable (optionnel)")
    # --- Série -----------------------------------------------------------
    parser.add_argument("--port", help="Port série (/dev/ttyUSB0, /dev/ttyACM1, ...)")
    parser.add_argument("--baudrate", type=int, default=115200, help="Baud rate (défaut 115200)")
    parser.add_argument(
        "--line-mode",
        action="store_true",
        help="Série : un paquet par ligne terminée par \\n (sinon par chunk lu)",
    )
    # --- Durée -----------------------------------------------------------
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Durée de capture en secondes (défaut 60 ; ≥ 600 recommandé pour la dérive horloge)",
    )
    # --- Extraction des champs du paquet (à renseigner après Q3/Q7) ------
    parser.add_argument(
        "--seq-offset", type=int, default=None, help="Offset du numéro de séquence dans le paquet"
    )
    parser.add_argument("--seq-size", type=int, default=4, help="Taille en octets du n° de séquence (défaut 4)")
    parser.add_argument(
        "--seq-endian",
        choices=["little", "big"],
        default="little",
        help="Endianness du n° de séquence (défaut little)",
    )
    parser.add_argument(
        "--sensor-ts-offset", type=int, default=None, help="Offset du timestamp capteur (ms)"
    )
    parser.add_argument(
        "--sensor-ts-size", type=int, default=4, help="Taille en octets du timestamp capteur (défaut 4)"
    )
    # --- Sortie -----------------------------------------------------------
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Fichier JSONL de sortie (le dossier parent est créé si absent ; refus d'écraser)",
    )
    return parser


def detect_transport() -> str:
    """Détection best-effort du transport réel (question 1).

    Ordre : ports série (déterministe) → adaptateur Bluetooth → sinon erreur.
    À confirmer avec ``detect_device.py`` et le capteur branché.
    """
    serial_ports = sorted(
        p.name for p in Path("/dev").glob("tty*") if p.name.startswith(("ttyUSB", "ttyACM"))
    )
    if serial_ports:
        print(
            f"[auto] port(s) série détecté(s) : {', '.join(serial_ports)} → transport 'serial'",
            file=sys.stderr,
        )
        return "serial"

    bt_dir = Path("/sys/class/bluetooth")
    adapters = sorted(bt_dir.glob("hci*")) if bt_dir.is_dir() else []
    if adapters:
        print(
            f"[auto] adaptateur BLE détecté : {', '.join(p.name for p in adapters)} → transport 'ble'",
            file=sys.stderr,
        )
        return "ble"

    raise SystemExit(
        "[auto] aucun transport détecté (ni port série, ni adaptateur BT).\n"
        "       Brancher le capteur puis relancer `uv run detect_device.py` pour diagnostiquer."
    )


def make_extraction(args: argparse.Namespace) -> ExtractionConfig | None:
    """Configuration d'extraction de champs, ou ``None`` si aucun offset fourni."""
    if args.seq_offset is None and args.sensor_ts_offset is None:
        return None
    return ExtractionConfig(
        seq_offset=args.seq_offset,
        seq_size=args.seq_size,
        seq_endian=args.seq_endian,
        sensor_ts_offset=args.sensor_ts_offset,
        sensor_ts_size=args.sensor_ts_size,
    )


def run_ble(args: argparse.Namespace, extraction: ExtractionConfig | None) -> None:
    """Capture BLE (asynchrone) puis fermeture propre du fichier JSONL."""
    import asyncio

    session = BleCaptureSession(
        on_packet=lambda payload: None,  # remplacé par run_ble_capture
        address=args.address,
        name_substr=args.name,
        service_uuid=args.service_uuid,
        char_uuid=args.char_uuid,
    )

    async def _run() -> None:
        writer = JsonlCaptureWriter(args.output, _header(args, "ble"))
        try:
            await run_ble_capture(writer, extraction, args.duration, session)
        finally:
            footer = writer.close(note="capture BLE terminée")
            print(
                f"[done] {footer['n_records']} paquets en {footer['duration_s']} s → {args.output}",
                file=sys.stderr,
            )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


def run_serial(args: argparse.Namespace, extraction: ExtractionConfig | None) -> None:
    """Capture série (synchronisée par thread de lecture) puis fermeture propre."""
    if not args.port:
        raise SystemExit("transport 'serial' : --port requis (ex. /dev/ttyUSB0)")
    session = SerialCaptureSession(
        on_packet=lambda payload: None,  # remplacé par run_serial_capture
        port=args.port,
        baudrate=args.baudrate,
        line_mode=args.line_mode,
    )
    writer = JsonlCaptureWriter(args.output, _header(args, "serial"))
    try:
        run_serial_capture(writer, extraction, args.duration, session)
    finally:
        footer = writer.close(note="capture série terminée")
        print(
            f"[done] {footer['n_records']} paquets en {footer['duration_s']} s → {args.output}",
            file=sys.stderr,
        )


def _header(args: argparse.Namespace, transport: str) -> dict[str, object]:
    """Header JSONL : trace les options de capture pour l'analyse a posteriori."""
    extraction = make_extraction(args)
    return {
        "transport": transport,
        "duration_requested_s": args.duration,
        "baudrate": args.baudrate if transport == "serial" else None,
        "line_mode": args.line_mode if transport == "serial" else None,
        "extraction": (
            None
            if extraction is None
            else {
                "seq_offset": extraction.seq_offset,
                "seq_size": extraction.seq_size,
                "seq_endian": extraction.seq_endian,
                "sensor_ts_offset": extraction.sensor_ts_offset,
                "sensor_ts_size": extraction.sensor_ts_size,
            }
        ),
    }


def main() -> int:
    args = build_parser().parse_args()
    transport = args.transport if args.transport != "auto" else detect_transport()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit(f"refus d'écraser un fichier existant : {args.output}")

    extraction = make_extraction(args)
    print(
        f"[start] transport={transport} durée={args.duration}s → {args.output}",
        file=sys.stderr,
    )
    if transport == "ble":
        run_ble(args, extraction)
    else:
        run_serial(args, extraction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
