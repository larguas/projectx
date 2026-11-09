#!/usr/bin/env python3
"""Génère l'échantillon de test synthétique ``backend/tests/data/sample_emg_imu.npz``.

**Données SYNTHÉTIQUES, déterministes (seed fixée), anonymisées** : aucun identifiant
de session/appareil/utilisateur n'est présent dans le fichier. Elles servent de
placeholder utilisable par les features 08/09 tant que la capture réelle du capteur
(spike 06b) n'a pas été produite ; elles seront remplacées par un extrait anonyme
d'une vraie capture dès que celle-ci existera (voir SENSOR_FINDINGS.md).

Contenu (2 s de signal) :
- ``emg_raw``     : float64 (4 canaux × 1000 échantillons), 500 Hz — bruit de base +
                    un burst d'activation (forme attendue par le simulateur de la f.07) ;
- ``imu_accel``   : float64 (3 axes × 200 échantillons), 100 Hz — gravité + micro-vibrations ;
- métadonnées     : ids de canaux, unités, fréquences (aucun identifiant personnel).

Usage (depuis scripts/sensor_spike/) :
    uv run make_sample_data.py            # écrit dans le backend/ du repo
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "backend" / "tests" / "data" / "sample_emg_imu.npz"

EMG_RATE_HZ = 500.0
IMU_RATE_HZ = 100.0
DURATION_S = 2.0
N_EMG_CHANNELS = 4


def make_emg(rng: np.random.Generator) -> np.ndarray:
    """Bruit de base + un burst d'activation (rectifié, en valeurs brutes int16-like)."""
    n = int(EMG_RATE_HZ * DURATION_S)
    emg = np.empty((N_EMG_CHANNELS, n), dtype=np.float64)
    for ch in range(N_EMG_CHANNELS):
        noise = rng.normal(0.0, 12.0, n)  # bruit de fond ~±36 (3σ) en valeurs brutes
        emg[ch] = noise

    # Burst d'activation : montée/exponentielle décroissante, phase légèrement décalée par canal.
    burst_start, burst_end = int(0.4 * EMG_RATE_HZ), int(1.2 * EMG_RATE_HZ)
    t = (np.arange(burst_start, burst_end) - burst_start) / EMG_RATE_HZ  # temps relatif au burst
    envelope = 900.0 * np.exp(-3.0 * (t - 0.05)) * np.clip((t - 0.0) / 0.05, 0.0, 1.0)
    for ch in range(N_EMG_CHANNELS):
        delay = int(ch * 0.01 * EMG_RATE_HZ)  # 10 ms de décalage par canal
        a, b = burst_start + delay, min(burst_end + delay, n)
        m = b - a
        emg[ch, a:b] += envelope[:m] * (1.0 + rng.normal(0.0, 0.05, m))
    return emg


def make_imu(rng: np.random.Generator) -> np.ndarray:
    """Accéléromètre : gravité sur z, micro-vibrations pendant le burst."""
    n = int(IMU_RATE_HZ * DURATION_S)
    imu = np.empty((3, n), dtype=np.float64)
    imu[0] = rng.normal(0.0, 0.02, n)          # x : bruit
    imu[1] = rng.normal(0.0, 0.02, n)          # y : bruit
    imu[2] = 9.81 + rng.normal(0.0, 0.02, n)   # z : gravité + bruit

    burst_start, burst_end = int(0.4 * IMU_RATE_HZ), int(1.2 * IMU_RATE_HZ)
    vib = 0.35 * np.sin(2 * np.pi * 8.0 * (np.arange(burst_end - burst_start) / IMU_RATE_HZ))
    for axis in range(3):
        imu[axis, burst_start:burst_end] += vib * rng.uniform(0.4, 1.0)
    return imu


def main() -> int:
    rng = np.random.default_rng(20261109)
    emg = make_emg(rng)
    imu = make_imu(rng)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUT_PATH,
        # EMG (data_type "emg_raw")
        emg_raw=emg,
        emg_channel_ids=np.array([f"ch_{i:02d}" for i in range(1, N_EMG_CHANNELS + 1)]),
        emg_units=np.array("raw"),
        emg_sample_rate=np.array(EMG_RATE_HZ),
        # IMU (data_type "imu_accel")
        imu_accel=imu,
        imu_axis_ids=np.array(["x", "y", "z"]),
        imu_units=np.array("m/s^2"),
        imu_sample_rate=np.array(IMU_RATE_HZ),
    )
    size_kb = OUT_PATH.stat().st_size / 1024.0
    print(
        f"écrit {OUT_PATH} ({size_kb:.1f} Ko) — "
        f"emg_raw {emg.shape} @ {EMG_RATE_HZ:.0f} Hz, imu_accel {imu.shape} @ {IMU_RATE_HZ:.0f} Hz"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
