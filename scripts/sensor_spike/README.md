# sensor_spike — Spike 06b « capteur réel »

Mini-projet **uv jetable**, indépendant du backend Django (pas de venv partagé,
pas d'import Django). Il sert uniquement à la feature 06b : lire le vrai
capteur EMG/IMU, mesurer ses capacités réelles, et produire les constats qui
valideront (ou corrigeront) le protocole supposé avant la feature 07.

## Installation

```bash
cd scripts/sensor_spike
uv sync          # crée .venv + uv.lock ; ne touche pas à l'environnement du backend
```

Dépendances : `bleak` (BLE), `pyserial` (série/USB-CDC), `numpy` (analyse).
La question 1 du spike (connexion réelle) n'étant pas tranchée, les deux
transports sont inclus ; **retirer l'inutilisé une fois Q1 mesurée**.

## Workflow

```bash
# 1. Identifier la connexion réelle (Q1) : USB, ports série, adaptateur BT, scan BLE
uv run detect_device.py

# 2. Capturer le flux brut (horodatage côté hôte : monotone + UTC), JSONL lisible a posteriori
uv run read_sensor.py --transport ble --name "EMG" --duration 600 \
    --output captures/cap_ble_10min.jsonl
# ou, en série :
uv run read_sensor.py --transport serial --port /dev/ttyUSB0 --baudrate 115200 \
    --duration 600 --output captures/cap_serial_10min.jsonl

# 3. Analyser (débit réel, jitter, pertes de séquence, dérive horloge 10/30 min)
uv run analyze_capture.py --input captures/cap_ble_10min.jsonl \
    --nominal-hz <débit nominal> --probe --report captures/rapport.json
```

## Fichier brut JSONL

- ligne 1 : `{"type": "header", ...}` — transport, durée demandée, options d'extraction ;
- lignes suivantes : un `{"type": "record", ...}` par paquet, avec
  `recv_ts_mono` (monotone hôte), `recv_ts_utc`, `payload_hex`, et `seq` /
  `sensor_ts_ms` **si** le capteur les expose (sinon `null`) ;
- dernière ligne : `{"type": "footer", ...}` — durée, compteurs.

Aucune valeur n'est inventée : un champ non exposé par le capteur reste `null`,
et l'analyse marque la métrique correspondante « inconnu » avec sa raison.

## Scripts

| Script | Rôle |
| --- | --- |
| `detect_device.py` | Détection de la connexion réelle (Q1) : `lsusb`, ports série, adaptateur BT, scan BLE. |
| `read_sensor.py` | Capture du flux → JSONL horodaté côté hôte. |
| `analyze_capture.py` | Les 4 métriques du spike sur une capture existante (`--probe` sonde les compteurs). |

## Modules pures (testables, sans I/O)

- `spike/parse.py` — extraction de champs par offsets + sonde heuristique de
  compteurs croissants (`probe_counters`) ;
- `spike/metrics.py` — débit, jitter, pertes de séquence, dérive d'horloge ;
- `spike/capture.py` — sessions BLE/série, écriture JSONL, relecture.
