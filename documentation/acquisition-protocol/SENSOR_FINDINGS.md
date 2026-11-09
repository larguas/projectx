# Constats capteur réel — Spike 06b

- **Date de session** : 2026-11-09
- **Statut** : ⚠️ **Phase 1 livrée (scripts + squelette) — mesures physiques à faire avec le capteur branché.**
- **Raison du statut** : au démarrage de la session, aucun capteur n'était connecté ni
  détectable sur la machine de dev :
  - `lsusb` : uniquement le hub racine et la tablette QEMU (aucun périphérique EMG/IMU) ;
  - aucun port série (`/dev/ttyUSB*`, `/dev/ttyACM*`) ;
  - aucun adaptateur Bluetooth (`/sys/class/bluetooth` vide).

Aucune valeur ci-dessous n'est inventée : chaque question sans mesure est marquée
**inconnu** avec sa raison. Les scripts du spike (`scripts/sensor_spike/`) sont prêts
et leur chaîne de traitement (écriture JSONL horodatée → analyse) a été validée sur
données synthétiques (`smoke_test_pipeline.py`).

## Questions à trancher avec le capteur

| # | Question | Réponse mesurée | Statut / raison |
|---|---|---|---|
| 1 | Connexion réelle : BLE, USB ou série ? Débit effectif ? Taille de paquet (MTU) ? | — | **inconnu** — capteur non connecté/détectable au démarrage de la session. À mesurer avec `uv run detect_device.py` puis une capture courte. |
| 2 | Fréquence d'échantillonnage réelle et stabilité (jitter) ? | — | **inconnu** — idem. À mesurer : `analyze_capture.py --nominal-hz <fréq. annoncée>` (débit observé, jitter p50/p95/σ). |
| 3 | Nombre de canaux EMG et IMU, et leur format de paquet ? | — | **inconnu** — idem. À observer sur la capture brute (taille des paquets, `--probe` pour repérer les compteurs/champs). |
| 4 | Nature du signal : RAW, rectifié ou enveloppe déjà calculée ? | — | **inconnu** — idem. À trancher en inspectant le signal (spectre/DC) sur l'enregistrement de repos et de contraction. |
| 5 | Unités, résolution (bits), gain, plage, échelle de conversion en µV ou valeurs brutes ? | — | **inconnu** — idem. À mesurer : amplitude au repos vs contraction, valeur max observée vs pleine échelle du convertisseur. |
| 6 | Timestamps : par échantillon, par paquet, ou aucun (à reconstruire côté client) ? | — | **inconnu** — idem. La capture horodate chaque paquet côté hôte (`recv_ts_mono` + `recv_ts_utc`) ; un timestamp capteur éventuel est extrait si l'offset est identifié (`--sensor-ts-offset`). |
| 7 | Compteur de paquets ou numéro de séquence dans le flux ? Détection des pertes possible ? | — | **inconnu** — idem. `analyze_capture.py --probe` sonde les positions « compteur croissant » ; à confirmer par un test de perte volontaire (Q9). |
| 8 | Dérive d'horloge du capteur sur 10 minutes et 30 minutes ? | — | **inconnu** — idem. Nécessite l'enregistrement continu 10 min (+ 30 min si possible) avec timestamp capteur exposé ; sinon la dérive est non mesurable (à noter). |
| 9 | Perte de paquets observée (BLE) pendant un mouvement réel ? | — | **inconnu** — idem. À mesurer sur l'enregistrement « mouvement répétitif » : `sequence_gaps` (manquants/doublons, taux de perte). |
| 10 | Informations de calibration ou d'identification exposées (numéro de série, firmware) ? | — | **inconnu** — idem. À vérifier : caractéristiques GATT de lecture / commandes série du capteur. |
| 11 | Comportement à la déconnexion/reconnexion (reprise du flux, doublons) ? | — | **inconnu** — idem. À tester sur l'enregistrement « déconnexion volontaire » : reprise du compteur, doublons, trous. |

## Enregistrements de référence à produire (checklist « à faire avec le capteur »)

Pré-requis : capteur branché, `cd scripts/sensor_spike && uv sync` déjà fait.
Chaque enregistrement = une capture JSONL dans `scripts/sensor_spike/captures/`.

- [ ] **0. Détection** — `uv run detect_device.py` → noter la connexion réelle (Q1) ;
      choisir le transport et retirer la dépendance inutilisée du spike (`pyproject.toml`).
- [ ] **1. Repos 30 s** — capteur en place, muscle relâché :
      `uv run read_sensor.py --transport <ble|serial> ... --duration 30 --output captures/01_repos_30s.jsonl`
      → Q2 (fréq. réelle au repos), Q4 (nature du signal), Q5 (amplitude de bruit).
- [ ] **2. Contraction volontaire maximale** — ~30 s :
      `--output captures/02_contraction_max_30s.jsonl` → Q4, Q5 (plage d'amplitude, saturation ?).
- [ ] **3. Mouvement répétitif (10 répétitions)** — ~60–120 s :
      `--output captures/03_mouvement_rep_10.jsonl` → Q9 (pertes pendant le mouvement), Q7 (trous de séquence).
- [ ] **4. 10 minutes continues** — au repos ou en activité légère :
      `--duration 600 --output captures/04_continu_10min.jsonl` → Q8 (dérive horloge fenêtre 10 min), Q2 (stabilité long terme).
- [ ] **5. 30 minutes continues** *(si le temps le permet)* —
      `--duration 1800 --output captures/05_continu_30min.jsonl` → Q8 (fenêtre 30 min).
- [ ] **6. Déconnexion volontaire** — couper le capteur ~10 s puis le rebrancher, pendant une capture :
      `--output captures/06_deconnexion_reprise.jsonl` → Q11 (reprise du flux, doublons, comportement du compteur).

Pour chaque enregistrement :
- [ ] lancer `uv run analyze_capture.py --input captures/<fichier>.jsonl --nominal-hz <fréq.> --probe --report captures/<fichier>.rapport.json` ;
- [ ] reporter les valeurs mesurées dans le tableau ci-dessus (remplacer « inconnu ») ;
- [ ] noter toute anomalie (paquets tronqués, silence, reconnexion automatique…).

## Décisions à prendre après mesures (à inscrire dans `shared/protocol/PROTOCOL.md`)

- [ ] Q1 tranchée → transport retenu et dépendance spike inutile retirée.
- [ ] Q3/Q7 → offsets réels du numéro de séquence et des timestamps capteur
      (à figer en exemple dans `PROTOCOL.md` et à utiliser dans `read_sensor.py`).
- [ ] Q8 → ordre de grandeur de la dérive : définit-il la tolérance de synchronisation
      d'horloge de la feature 07 (`clock_offset_ms`) ?
- [ ] Q9 → le JSON gzip suffit-il pour le transport client→backend, ou un format binaire
      est-il justifié (critère de `07-ingestion.md` : « seulement si le spike montre que
      le JSON ne suffit pas ») ?

## Point d'entrée code

- Scripts : `scripts/sensor_spike/README.md` (workflow complet).
- Protocole supposé (point de départ, à aligner ici-dessus) : `shared/protocol/PROTOCOL.md`.
- Consommateur en aval : `backend/docs/07-ingestion.md` (mis à jour avec les décisions).
