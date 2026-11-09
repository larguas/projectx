#!/usr/bin/env python3
"""Détection du matériel capteur (tâche 1 du spike 06b).

Avant d'écrire le lecteur, on documente ce qui est physiquement observable :
- périphériques USB        -> `lsusb` (subprocess)
- ports série              -> pyserial (`list_ports`) + /dev/tty*
- adaptateur Bluetooth     -> /sys/class/bluetooth + D-Bus (via bleak si dispo)
- scan BLE                 -> bleak (si un adaptateur existe)

Usage:
    uv run python detect_device.py            # rapport lisible sur stdout
    uv run python detect_device.py --json     # rapport JSON (pour SENSOR_FINDINGS.md)
    uv run python detect_device.py --ble-timeout 15

Aucune valeur n'est inventée : ce script ne fait que reporter ce qu'il voit.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class PortInfo:
    device: str
    description: str = ""
    hwid: str = ""


@dataclass
class DetectionReport:
    hostname: str
    system: str
    usb_devices: list[str] = field(default_factory=list)
    usb_error: str = ""
    serial_ports: list[PortInfo] = field(default_factory=list)
    tty_devices: list[str] = field(default_factory=list)
    bluetooth_adapters: list[str] = field(default_factory=list)
    ble_scan: list[dict] = field(default_factory=list)
    ble_scan_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect_usb() -> tuple[list[str], str]:
    """Sorties brutes de `lsusb` (une ligne par périphérique)."""
    if shutil.which("lsusb") is None:
        return [], "lsusb introuvable sur cette machine"
    try:
        proc = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=15, check=False
        )
    except subprocess.TimeoutExpired:
        return [], "lsusb en timeout"
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines, (proc.stderr.strip() if proc.returncode != 0 else "")


def detect_serial_ports() -> list[PortInfo]:
    ports: list[PortInfo] = []
    try:
        from serial.tools.list_ports import comports

        for p in comports():
            ports.append(PortInfo(device=p.device, description=p.description, hwid=p.hwid or ""))
    except Exception as exc:  # noqa: BLE001 — pyserial doit toujours rester optionnel
        print(f"[warn] list_ports indisponible : {exc}", file=sys.stderr)
    return ports


def detect_tty_devices() -> list[str]:
    """Fichiers /dev/ttyUSB* et /dev/ttyACM* (périphériques série Linux)."""
    dev = Path("/dev")
    found: list[str] = []
    for pattern in ("ttyUSB*", "ttyACM*"):
        found.extend(sorted(p.name for p in dev.glob(pattern)))
    return found


def detect_bluetooth_adapters() -> list[str]:
    """Adaptateurs HCI exposés par le noyau Linux."""
    cls = Path("/sys/class/bluetooth")
    if not cls.is_dir():
        return []
    return sorted(p.name for p in cls.iterdir())


def ble_scan(timeout_s: float) -> tuple[list[dict], str]:
    """Scan BLE via bleak. Retourne la liste des appareils vus (nom, adresse, RSSI)."""
    try:
        from bleak import BleakScanner
    except Exception as exc:  # noqa: BLE001
        return [], f"bleak indisponible : {exc}"

    found: dict[str, dict] = {}

    def on_device(device, _advertising_data) -> None:
        found[device.address] = {
            "address": device.address,
            "name": device.name or "",
            "rssi": getattr(_advertising_data, "rssi", None),
        }

    try:
        devices = BleakScanner.discover(timeout=timeout_s, service_uuids=None)
    except Exception as exc:  # noqa: BLE001 — ex. « No default Bluetooth adapter found »
        return [], f"scan impossible : {exc}"
    for d in devices:
        found[d.address] = {"address": d.address, "name": d.name or "", "rssi": None}
    # on_device peut enrichir avec le RSSI si la version de bleak le fournit
    return sorted(found.values(), key=lambda x: x["address"]), ""


def build_report(ble_timeout: float) -> DetectionReport:
    usb, usb_err = detect_usb()
    report = DetectionReport(
        hostname=platform.node(),
        system=f"{platform.system()} {platform.release()} ({platform.machine()})",
        usb_devices=usb,
        usb_error=usb_err,
        serial_ports=detect_serial_ports(),
        tty_devices=detect_tty_devices(),
        bluetooth_adapters=detect_bluetooth_adapters(),
    )
    if report.bluetooth_adapters:
        report.ble_scan, report.ble_scan_error = ble_scan(ble_timeout)
    else:
        report.ble_scan_error = "aucun adaptateur Bluetooth (/sys/class/bluetooth vide)"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument(
        "--ble-timeout", type=float, default=10.0, help="durée du scan BLE en secondes"
    )
    args = parser.parse_args()

    report = build_report(args.ble_timeout)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"Machine : {report.hostname} — {report.system}")
    print("\n[USB] lsusb :")
    if report.usb_devices:
        for line in report.usb_devices:
            print(f"  {line}")
    else:
        print("  (aucun périphérique)")
    if report.usb_error:
        print(f"  [warn] {report.usb_error}")

    print("\n[Série] ports (pyserial) :")
    if report.serial_ports:
        for p in report.serial_ports:
            print(f"  {p.device} — {p.description} [{p.hwid}]")
    else:
        print("  (aucun)")
    print("[Série] /dev/tty* :")
    print(f"  {', '.join(report.tty_devices) if report.tty_devices else '(aucun)'}")

    print("\n[Bluetooth] adaptateurs :")
    print(f"  {', '.join(report.bluetooth_adapters) if report.bluetooth_adapters else '(aucun)'}")
    if report.ble_scan:
        print("[BLE] appareils détectés :")
        for d in report.ble_scan:
            rssi = f" (RSSI {d['rssi']} dBm)" if d.get("rssi") is not None else ""
            print(f"  {d['address']} — {d['name'] or '(sans nom)'}{rssi}")
    elif report.ble_scan_error:
        print(f"[BLE] scan : {report.ble_scan_error}")

    # Conclusion factuelle, sans interprétation du protocole.
    candidates = bool(report.serial_ports or report.tty_devices or report.ble_scan)
    print(
        "\nConclusion : "
        + (
            "au moins un port candidat observé — voir liste ci-dessus."
            if candidates
            else "aucun capteur apparent (ni USB inconnu, ni série, ni BLE)."
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
