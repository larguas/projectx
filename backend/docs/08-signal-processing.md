# Feature 08 — Moteur de traitement du signal EMG/IMU

## Objectif
Bibliothèque Python pure (NumPy/SciPy), **sans dépendance à Django**, qui valide, filtre et extrait des indicateurs. Indépendante des autres features (peut être faite en parallèle après la 01).

## Périmètre
Qualité du signal, prétraitement EMG, features EMG, traitement IMU de base, versionnement des algorithmes.

## Hors périmètre
Orchestration Celery, stockage en base, IA.

## Emplacement
`backend/apps/signal_processing/engine/` (package sans import Django). Un petit adaptateur Django viendra en feature 09.

```text
engine/
├── __init__.py          # ALGORITHM_VERSION
├── types.py             # dataclasses : Signal, ProcessingParams, FeatureResult
├── quality.py
├── preprocessing.py     # filtres, rectification, enveloppe
├── features_emg.py
├── imu.py
├── windows.py
├── pipeline.py          # enchaîne les étapes, retourne résultats + paramètres utilisés
└── io.py                # lecture CSV / npz vers Signal
```

## Tâches

### Types et conventions
- [ ] `Signal` : `samples` (ndarray, canaux x temps), `sample_rate`, `data_type` (`emg_raw`, `emg_rectified`, `emg_envelope`, ...), `units`, `calibration`.
- [ ] `ProcessingParams` (dataclass sérialisable en dict/JSON) : tous les paramètres de filtrage configurables, avec valeurs par défaut documentées.
- [ ] `ALGORITHM_VERSION` (semver) incrémenté à chaque changement d'algorithme.
- [ ] Ne jamais appliquer automatiquement les mêmes traitements à tous les types : le pipeline adapte les étapes à `data_type` (un signal déjà rectifié/enveloppe ne se re-filtre pas).

### Qualité du signal
- [ ] Détection des échantillons manquants/NaN, gaps d'horodatage.
- [ ] Détection de saturation (plage configurable).
- [ ] Vérification de la fréquence d'échantillonnage réelle vs déclarée.
- [ ] Rapport de qualité structuré (score, alertes, plages problématiques).

### Prétraitement EMG
- [ ] Filtre passe-bande Butterworth (zéro-phase, `sosfiltfilt`), bornes configurables.
- [ ] Notch 50 Hz optionnel (60 Hz configurable).
- [ ] Rectification, enveloppe (passe-bas ou fenêtre RMS glissante), RMS.
- [ ] Gestion des fréquences d'échantillonnage trop basses (erreur explicite si Nyquist non respecté).

### Features EMG (par fenêtre)
- [ ] RMS, MAV, iEMG, Peak, Mean Frequency, Median Frequency (via Welch), Zero Crossing, Waveform Length.
- [ ] Activation : seuil (baseline + k·écart-type, paramétrable), `activation_duration`, `activation_ratio`, détection des phases actives.
- [ ] Fenêtrage : durée et recouvrement configurables, résultats alignés sur le temps.

### IMU
- [ ] Norme de l'accélération, vitesse angulaire.
- [ ] Détection de répétitions (pics/creux sur un signal de référence, paramètres configurables).
- [ ] Segmentation des phases (montée/descente), durée de phase, régularité (variabilité inter-répétitions).
- [ ] Orientation seulement si fournie par le capteur ; sinon non calculée.

### Résultats et traçabilité
- [ ] Chaque calcul retourne un `FeatureResult` contenant : valeurs, `algorithm_version`, `params` utilisés, `sample_rate`, métadonnées d'entrée.
- [ ] Sérialisation JSON/numpy des résultats.
- [ ] Normalisation MVC optionnelle (fournie en paramètre, jamais appliquée implicitement).

## Tests (scientifiques)
- Signaux synthétiques : sinus connu pour valider fréquences/RMS ; bruit blanc ; sinus + 50 Hz pour valider le notch ; signal saturé ; signal avec trous.
- Median/Mean frequency sur signal de fréquence connue (tolérance).
- Détection de répétitions sur signal sinusoïdal à n cycles.
- Reproductibilité : mêmes params ⇒ mêmes résultats.
- Test que le package n'importe pas Django (`import django` interdit dans `engine/`).

## Critères d'acceptation
- `engine.pipeline.run(signal, params)` fonctionne sur un CSV d'exemple (fixture dans `tests/data/`).
- Couverture élevée sur `engine/` (≥ 90 %).
- `make check` passe.
