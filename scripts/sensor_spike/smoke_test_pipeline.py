"""Test de fumée du pipeline d'analyse (données SYNTHÉTIQUES, pas des données capteur).

Génère une capture JSONL aux propriétés connues :
- 500 paquets/s pendant 20 s ;
- un trou de séquence (5 numéros manquants) au milieu ;
- dérive d'horloge capteur de +10 ppm.
Vérifie que analyze_capture.py les retrouve.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from spike.capture import CaptureRecord, JsonlCaptureWriter  # noqa: E402


def make_capture(path: Path) -> None:
    writer = JsonlCaptureWriter(path, {"transport": "synthetic", "duration_requested_s": 20.0})
    seq = 1000
    t0 = 1_000_000.0
    for i in range(10_000):  # 500 Hz × 20 s
        if 4_990 <= i < 4_995:  # trou : on saute 5 numéros de séquence
            seq += 1
        t = t0 + i / 500.0
        sensor_ms = (t - t0) * 1000.0 * 1.00001  # dérive +10 ppm
        payload = (i & 0xFFFFFFFF).to_bytes(4, "little") + (seq & 0xFFFFFFFF).to_bytes(4, "big")
        writer.record(
            CaptureRecord(
                recv_ts_mono=t,
                recv_ts_utc="2026-11-09T00:00:00.000Z",
                payload=payload,
                seq=seq,
                sensor_ts_ms=sensor_ms,
            )
        )
        seq += 1
    writer.close(note="synthetic smoke test")


def main() -> int:
    with tempfile.TemporaryDirectory(dir="/tmp/opencode") as tmp:
        cap = Path(tmp) / "synthetic.jsonl"
        make_capture(cap)
        report = Path(tmp) / "report.json"
        proc = subprocess.run(
            [
                sys.executable, "analyze_capture.py",
                "--input", str(cap),
                "--nominal-hz", "500",
                "--probe",
                "--report", str(report),
            ],
            capture_output=True, text=True, cwd=str(Path(__file__).parent),
        )
        print(proc.stdout)
        assert proc.returncode == 0, proc.stderr
        data = json.loads(report.read_text())

        # Débit : ~500 paquets/s
        assert abs(data["throughput"]["records_per_s"] - 500) < 2, data["throughput"]
        # Perte de séquence : 5 manquants détectés
        assert data["sequence"]["missing_count"] == 5, data["sequence"]
        # Dérive : ~+10 ppm retrouvée (tolérance large, régression sur 20 s)
        drift = data["clock_drift"]["drift_ppm"]
        assert abs(drift - 10.0) < 2.0, drift
        # Sonde de compteurs : le byte bas du seq (big-endian → offset 7) doit être
        # candidat. La sonde ne teste que little-endian (heuristique) ; l'endian réel
        # se confirme ensuite avec --seq-endian sur le candidat identifié.
        probe = data.get("counter_probe", [])
        assert any(c["offset"] == 7 and c["size_bytes"] == 1 for c in probe), probe

    print("SMOKE TEST OK : débit, pertes de séquence, dérive et sonde de compteurs vérifiés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
