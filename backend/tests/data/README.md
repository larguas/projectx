# backend/tests/data/ — échantillons de données

Échantillons utilisables par les tests des features en aval (08 traitement du signal,
09 analytics).

## `sample_emg_imu.npz`

**Données SYNTHÉTIQUES, déterministes (seed 20261109), anonymisées** : aucun identifiant
de session, d'appareil ou d'utilisateur n'est présent dans le fichier. C'est un
placeholder utilisable par les features 08/09 tant que la capture réelle du capteur
(spike 06b) n'a pas été produite ; à remplacer par un extrait anonyme d'une vraie
capture dès que celle-ci existe (voir
`documentation/acquisition-protocol/SENSOR_FINDINGS.md`).

Contenu (2 s de signal, forme `canaux × temps`) :

| Clé | Shape | Description |
|---|---|---|
| `emg_raw` | (4, 1000) float64 | EMG brut simulé, 500 Hz — bruit de fond + burst d'activation (0,4–1,2 s) |
| `emg_channel_ids` | (4,) str | `ch_01`…`ch_04` |
| `emg_units` | scalar str | `"raw"` |
| `emg_sample_rate` | scalar float | 500.0 Hz |
| `imu_accel` | (3, 200) float64 | Accéléromètre simulé, 100 Hz — gravité sur z + micro-vibrations pendant le burst |
| `imu_axis_ids` | (3,) str | `x`, `y`, `z` |
| `imu_units` | scalar str | `"m/s^2"` |
| `imu_sample_rate` | scalar float | 100.0 Hz |

**Choix du format : npz** (et non CSV) — le backend dépend déjà de `numpy`/`scipy` et la
feature 08 consomme des ndarrays `(canaux × temps)` ; un npz se charge directement avec
`np.load(..., allow_pickle=False)`, sans couche de parsing.

Régénération (déterministe, même seed → même fichier) :

```bash
cd scripts/sensor_spike && uv run python make_sample_data.py
```
