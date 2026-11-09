#!/usr/bin/env python3
"""Analyse d'une capture JSONL du spike 06b — métriques pures, sans ré-enregistrement.

Les quatre métriques minimales exigées par le doc 06b :
1. débit réel        (paquets/s, et échantillons/s vs nominal si fourni) ;
2. jitter            (variabilité des inter-arrivées, timestamps monotones hôte) ;
3. pertes de séquence (trous/doublons dans le compteur du capteur, si exposé) ;
4. dérive d'horloge  (capteur vs hôte : globale + fenêtres 10/30 min, si timestamp).

Une métrique dont la donnée source est absente de la capture est marquée
``{"ok": false, "reason": ...}`` — jamais de valeur inventée.

Usage :
    uv run analyze_capture.py --input captures/cap_60s.jsonl
    uv run analyze_capture.py --input cap.jsonl --nominal-hz 500 --probe
    uv run analyze_capture.py --input cap.jsonl --report rapport.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from spike.capture import load_capture
from spike.metrics import (
    clock_drift_report,
    jitter_report,
    observed_rate,
    sample_rate_report,
    sequence_gaps,
    windowed_clock_drift,
)
from spike.parse import probe_counters

DRIFT_WINDOWS_S = (600.0, 1800.0)  # fenêtres 10 min et 30 min exigées par le doc 06b


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyse d'une capture JSONL du spike 06b.")
    parser.add_argument("--input", required=True, type=Path, help="Fichier de capture JSONL")
    parser.add_argument(
        "--nominal-hz",
        type=float,
        default=None,
        help="Débit nominal attendu (paquets/s) pour la comparaison d'écart",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Sonde heuristique des compteurs croissants dans les paquets (aide à la Q7)",
    )
    parser.add_argument("--report", type=Path, default=None, help="Écrit aussi le rapport JSON ici")
    return parser


def _duration_s(records: list[dict[str, Any]], footer: dict[str, Any] | None) -> float:
    """Durée de capture : écart monotone premier→dernier paquet (fenêtre d'arrivée réelle).

    Le ``duration_s`` du footer inclut la mise en route et l'arrêt ; l'écart entre
    les timestamps des paquets est le dénominateur honnête pour le débit observé.
    Repli sur le footer si moins de 2 enregistrements.
    """
    if len(records) >= 2:
        return records[-1]["recv_ts_mono"] - records[0]["recv_ts_mono"]
    if footer and footer.get("duration_s") is not None:
        return float(footer["duration_s"])
    return 0.0


def analyze(
    records: list[dict[str, Any]],
    footer: dict[str, Any] | None,
    nominal_hz: float | None = None,
) -> dict[str, Any]:
    """Calcule les quatre métriques sur une capture rechargée (fonction pure)."""
    n = len(records)
    mono = [r["recv_ts_mono"] for r in records]
    duration = _duration_s(records, footer)

    report: dict[str, Any] = {
        "n_records": n,
        "duration_s": round(duration, 3),
        "throughput": observed_rate(n, duration),
        "jitter": jitter_report(
            mono, nominal_period_s=(1.0 / nominal_hz if nominal_hz else None)
        ),
    }
    if nominal_hz is not None:
        report["sample_rate"] = sample_rate_report(n, duration, nominal_hz)

    seqs = [r["seq"] for r in records if r.get("seq") is not None]
    if seqs:
        report["sequence"] = sequence_gaps(seqs)
    else:
        report["sequence"] = {
            "ok": False,
            "reason": "aucun numéro de séquence dans la capture (champ null — capteur non exposé ou offsets non renseignés)",
        }

    pairs = [
        (r["recv_ts_mono"], r["sensor_ts_ms"])
        for r in records
        if r.get("sensor_ts_ms") is not None
    ]
    if len(pairs) >= 10:
        host = [p[0] for p in pairs]
        sensor = [p[1] for p in pairs]
        report["clock_drift"] = clock_drift_report(sensor, host)
        report["clock_drift_windows"] = {
            f"{int(window)}s": windowed_clock_drift(sensor, host, window)
            for window in DRIFT_WINDOWS_S
        }
    else:
        report["clock_drift"] = {
            "ok": False,
            "reason": "pas de timestamp capteur dans la capture (champ null — capteur non exposé ou offsets non renseignés)",
        }
    return report


def probe_payloads(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sonde heuristique des positions « compteur croissant » (aide à la Q7).

    Retourne les candidats triés par qualité ; une liste vide est une réponse
    légitime (pas de compteur détectable sur cette capture).
    """
    payloads = [bytes.fromhex(r["payload_hex"]) for r in records if r.get("payload_hex")]
    return [c.__dict__ | {"label": c.label} for c in probe_counters(payloads)]


def print_report(header: dict[str, Any], report: dict[str, Any]) -> None:
    """Impression lisible du rapport (stdout) — le JSON complet passe par --report."""
    transport = header.get("transport", "inconnu")
    print(f"Capture : transport={transport}, {report['n_records']} paquets, {report['duration_s']} s")

    tp = report["throughput"]
    print(f"  débit        : {tp['records_per_s']} paquets/s")
    if "sample_rate" in report:
        sr = report["sample_rate"]
        print(
            f"                nominal={sr.get('nominal_hz')} Hz → observé={sr['observed_hz']} Hz "
            f"(écart {sr.get('deviation_pct')} %)"
        )

    j = report["jitter"]
    if j.get("ok"):
        print(
            f"  jitter       : moy={j['mean_ms']} ms, σ={j['std_ms']} ms, "
            f"p95={j['p95_ms']} ms, max={j['max_ms']} ms"
        )
    else:
        print(f"  jitter       : inconnu — {j.get('reason')}")

    s = report["sequence"]
    if s.get("ok"):
        print(
            f"  séquence     : {s['first']}→{s['last']}, manquants={s['missing_count']}, "
            f"doublons={s['duplicate_count']}, perte={s['loss_rate_pct']} %"
        )
    else:
        print(f"  séquence     : inconnu — {s.get('reason')}")

    d = report["clock_drift"]
    if d.get("ok"):
        print(
            f"  dérive       : {d['drift_ppm']} ppm (pente {d['slope_ms_per_host_s']} ms/s, "
            f"total {d['total_drift_ms']} ms sur {d['duration_s']} s)"
        )
        for label, w in report.get("clock_drift_windows", {}).items():
            if w.get("ok"):
                reached = "" if w.get("window_reached") else " [fenêtre non atteinte]"
                print(f"    fenêtre {label}: {w['drift_ppm']} ppm{reached}")
    else:
        print(f"  dérive       : inconnu — {d.get('reason')}")


def main() -> int:
    args = build_parser().parse_args()
    if not args.input.exists():
        raise SystemExit(f"fichier de capture introuvable : {args.input}")

    header, records, footer = load_capture(args.input)
    if not records:
        raise SystemExit("aucun enregistrement dans la capture")

    report = analyze(records, footer, nominal_hz=args.nominal_hz)
    print_report(header, report)

    if args.probe:
        candidates = probe_payloads(records)
        if candidates:
            print("\nSonde de compteurs (candidats pour --seq-offset, par qualité décroissante) :")
            for c in candidates:
                print(
                    f"  {c['label']} : fraction croissante={c['fraction_increasing']:.3f}, "
                    f"début={c['start_value']}, fin={c['end_value']}"
                )
        else:
            print("\nSonde de compteurs : aucun candidat détectable sur cette capture.")

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        payload = {"capture": str(args.input), "header": header, **report}
        if args.probe:
            payload["counter_probe"] = probe_payloads(records)
        args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nRapport JSON écrit → {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
