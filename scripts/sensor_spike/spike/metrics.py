"""Métriques d'analyse de capture — fonctions pures (numpy), sans I/O ni Django.

Les quatre métriques minimales exigées par le spike 06b :
- débit réel        -> ``observed_rate`` / ``sample_rate_report``
- jitter            -> ``jitter_report`` (variabilité des inter-arrivées)
- pertes de séquence -> ``sequence_gaps`` (trous dans le compteur)
- dérive d'horloge  -> ``clock_drift_report`` (+ fenêtres 10/30 min)

Toutes les fonctions renvoient des dicts JSON-serialisables. Quand une donnée
n'est pas disponible (ex. pas de timestamp capteur), c'est l'appelant qui doit
marquer la métrique « inconnu » : ces fonctions ne devinent rien.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


def observed_rate(n_records: int, duration_s: float) -> dict[str, Any]:
    """Débit de paquets observé (paquets/s)."""
    if duration_s <= 0:
        return {"records": n_records, "duration_s": duration_s, "records_per_s": None}
    return {
        "records": n_records,
        "duration_s": round(duration_s, 3),
        "records_per_s": round(n_records / duration_s, 3),
    }


def sample_rate_report(
    n_samples: int, duration_s: float, nominal_hz: float | None = None
) -> dict[str, Any]:
    """Débit d'échantillons observé vs nominal (si fourni)."""
    out: dict[str, Any] = {
        "samples": n_samples,
        "duration_s": round(duration_s, 3),
        "observed_hz": round(n_samples / duration_s, 3) if duration_s > 0 else None,
    }
    if nominal_hz is not None and out["observed_hz"] is not None:
        deviation_pct = (out["observed_hz"] - nominal_hz) / nominal_hz * 100.0
        out["nominal_hz"] = nominal_hz
        out["deviation_pct"] = round(deviation_pct, 3)
    return out


def jitter_report(
    mono_timestamps: Sequence[float], nominal_period_s: float | None = None
) -> dict[str, Any]:
    """Variabilité des inter-arrivées (ms), sur timestamps monotones hôte.

    ``nominal_period_s`` : période théorique d'arrivée (1/fréquence de paquets).
    Si fournie, on compare l'écart-type observé à la période nominale.
    """
    ts = np.asarray(mono_timestamps, dtype=float)
    if ts.size < 3:
        return {"n": int(ts.size), "ok": False, "reason": "moins de 3 enregistrements"}
    intervals_ms = np.diff(ts) * 1000.0
    out: dict[str, Any] = {
        "n": int(ts.size),
        "ok": True,
        "mean_ms": round(float(np.mean(intervals_ms)), 4),
        "std_ms": round(float(np.std(intervals_ms, ddof=1)), 4),
        "p50_ms": round(float(np.percentile(intervals_ms, 50)), 4),
        "p95_ms": round(float(np.percentile(intervals_ms, 95)), 4),
        "max_ms": round(float(np.max(intervals_ms)), 4),
        "min_ms": round(float(np.min(intervals_ms)), 4),
    }
    if nominal_period_s is not None and nominal_period_s > 0:
        out["nominal_period_ms"] = round(nominal_period_s * 1000.0, 4)
        out["std_over_nominal_pct"] = round(
            float(np.std(intervals_ms, ddof=1)) / (nominal_period_s * 1000.0) * 100.0, 3
        )
    return out


def sequence_gaps(sequence_numbers: Sequence[int]) -> dict[str, Any]:
    """Trous et doublons dans une suite de numéros de séquence.

    Attend des entiers ; la première valeur observée sert d'origine (le compteur
    du capteur peut démarrer à n'importe quelle valeur). ``gaps`` est borné à
    50 entrées pour rester lisible.
    """
    values = [int(v) for v in sequence_numbers]
    if not values:
        return {"n": 0, "ok": False, "reason": "aucun numéro de séquence"}

    first, last = values[0], values[-1]
    expected_count = last - first + 1
    unique = sorted(set(values))
    n_duplicates = len(values) - len(unique)

    gaps: list[dict[str, int]] = []
    prev = first
    for v in unique:
        if v > prev + 1:
            gaps.append({"from": prev, "to": v, "missing": v - prev - 1})
        prev = v

    total_missing = sum(g["missing"] for g in gaps)
    out: dict[str, Any] = {
        "n": len(values),
        "ok": True,
        "first": first,
        "last": last,
        "expected_count": expected_count,
        "missing_count": total_missing,
        "duplicate_count": n_duplicates,
        "loss_rate_pct": round(total_missing / max(expected_count, 1) * 100.0, 4),
        "gaps": gaps[:50],
        "n_gaps_truncated": max(0, len(gaps) - 50),
    }
    return out


def clock_drift_report(sensor_ts_ms: Sequence[float], host_mono_s: Sequence[float]) -> dict[str, Any]:
    """Dérive de l'horloge capteur vs horloge hôte sur toute la capture.

    Méthode : régression linéaire ``sensor_ts_ms ~ a * host_s + b``.
    - pente ``a`` en ms d'horloge capteur par seconde d'horloge hôte ;
    - ``drift_ppm`` = (a/1000 − 1) × 1e6 : écart relatif des deux horloges ;
    - ``total_drift_ms`` : écart cumulé entre les accroissements capteur et hôte.

    Renvoie ``ok: False`` si la capture est trop courte pour être significative.
    """
    sensor = np.asarray(sensor_ts_ms, dtype=float)
    host = np.asarray(host_mono_s, dtype=float)
    n = min(sensor.size, host.size)
    if n < 10 or host[-1] - host[0] < 5.0:
        return {"ok": False, "reason": "capture trop courte (< 10 points ou < 5 s)"}

    sensor, host = sensor[:n], host[:n]
    slope, intercept = np.polyfit(host, sensor, 1)  # pente en ms/s
    r_squared = _r_squared(sensor, host, slope, intercept)

    total_drift_ms = (sensor[-1] - sensor[0]) - (host[-1] - host[0]) * 1000.0
    return {
        "ok": True,
        "n": int(n),
        "duration_s": round(float(host[-1] - host[0]), 3),
        "slope_ms_per_host_s": round(float(slope), 4),
        "drift_ppm": round((float(slope) / 1000.0 - 1.0) * 1e6, 2),
        "total_drift_ms": round(float(total_drift_ms), 3),
        "r_squared": round(float(r_squared), 5),
    }


def windowed_clock_drift(
    sensor_ts_ms: Sequence[float], host_mono_s: Sequence[float], window_s: float
) -> dict[str, Any]:
    """Dérive sur la première fenêtre de ``window_s`` secondes de la capture.

    Si la capture est plus courte que la fenêtre, le calcul porte sur la durée
    disponible et ``window_reached`` vaut False (à signaler dans le constats).
    """
    sensor = np.asarray(sensor_ts_ms, dtype=float)
    host = np.asarray(host_mono_s, dtype=float)
    n = min(sensor.size, host.size)
    if n < 2:
        return {"ok": False, "reason": "capture trop courte"}

    t0 = host[0]
    mask = host[:n] <= t0 + window_s
    sensor_w, host_w = sensor[:n][mask], host[:n][mask]
    result = clock_drift_report(sensor_w, host_w)
    result["window_s"] = window_s
    result["window_reached"] = bool(host_w.size and (host_w[-1] - t0) >= window_s - 0.5)
    return result


def _r_squared(y: np.ndarray, x: np.ndarray, slope: float, intercept: float) -> float:
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot == 0.0 or math.isnan(ss_res):
        return float("nan")
    return 1.0 - ss_res / ss_tot
