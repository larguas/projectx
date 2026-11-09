# Feature 06b — Spike capteur (à faire avant la feature 07)

## Objectif
Valider avec le **vrai capteur** les hypothèses du protocole avant de les figer dans l'ingestion. Sans ça, l'ingestion risque d'être propre mais mal adaptée au matériel.

Cette session est en partie manuelle : elle demande le capteur physique. opencode peut écrire les scripts, mais les mesures et les décisions viennent de toi.

## Périmètre
Un script jetable de lecture du capteur, un fichier de constats, une mise à jour du protocole.

## Hors périmètre
Module PC complet (phase 5 de la roadmap générale), tout ce qui touche Django.

## Questions à trancher avec le capteur
1. Connexion réelle : BLE, USB ou série ? Débit effectif ? Taille de paquet (MTU) ?
2. Fréquence d'échantillonnage réelle et stabilité (jitter) ?
3. Nombre de canaux EMG et IMU, et leur format de paquet ?
4. Nature du signal : RAW, rectifié ou enveloppe déjà calculée ?
5. Unités, résolution (bits), gain, plage, échelle de conversion en µV ou en valeurs brutes ?
6. Timestamps : par échantillon, par paquet, ou aucun (à reconstruire côté client) ?
7. Compteur de paquets ou numéro de séquence dans le flux ? Détection des pertes possible ?
8. Dérive d'horloge du capteur sur 10 minutes et 30 minutes ?
9. Perte de paquets observée (BLE) pendant un mouvement réel ?
10. Informations de calibration ou d'identification exposées (numéro de série, firmware) ?
11. Comportement à la déconnexion/reconnexion (reprise du flux, doublons) ?

## Tâches
- [x] Script `scripts/sensor_spike/read_sensor.py` (uv, dépendances jetables : `bleak` ou `pyserial`) qui lit le flux et écrit un fichier brut horodaté. *(livré 2026-11-09 ; chaîne de traitement validée sur données synthétiques — capture réelle en attente du capteur)*
- [ ] Enregistrements de référence : repos 30 s, contraction volontaire maximale, mouvement répétitif (10 répétitions), 10 minutes continues, déconnexion volontaire. *(bloqué : capteur non connecté/détectable au démarrage de la session — checklist dans `SENSOR_FINDINGS.md`)*
- [x] Script d'analyse rapide : débit réel, jitter, pertes de séquence, dérive. *(livré 2026-11-09 : `analyze_capture.py`, métriques pures testées par `smoke_test_pipeline.py`)*
- [x] Rédiger `documentation/acquisition-protocol/SENSOR_FINDINGS.md` avec les réponses aux 11 questions. *(squelette livré 2026-11-09 : 11 × « inconnu » + raison, conforme au critère d'acceptation)*
- [x] Committer un petit échantillon anonyme dans `backend/tests/data/` (CSV ou npz) utilisable par les features 08 et 09. *(npz synthétique déterministe `sample_emg_imu.npz`, choix documenté dans le README du dossier)*
- [ ] Mettre à jour `shared/protocol/PROTOCOL.md` et `block.schema.json` : champs réellement disponibles, encodage retenu (JSON gzip seul, ou binaire en plus), taille de bloc recommandée, gestion des timestamps. *(partiel 2026-11-09 : doc + schéma créés depuis le protocole supposé, décisions structurantes prises et champs marqués « à valider » ; l'alignement sur les capacités réelles reste à faire après les mesures — voir `SENSOR_FINDINGS.md`)*
- [x] Décider : un seul `data_type` par bloc ou plusieurs ; flux EMG et IMU dans le même bloc ou séparés. *(décidé 2026-11-09 : un seul `data_type` par bloc, EMG et IMU en blocs séparés — justification dans `PROTOCOL.md` §2)*
- [x] Mettre à jour `07-ingestion.md` avec les décisions prises (écarts par rapport au protocole supposé). *(mis à jour 2026-11-09 : statut phase 1 + décisions structurantes ; aucun écart mesuré pour l'instant)*

## Critères d'acceptation
- `SENSOR_FINDINGS.md` répond aux 11 questions (ou note « inconnu » avec la raison).
- Le protocole 1.0 est aligné sur les capacités réelles du capteur.
- Un fichier d'exemple réel est disponible pour les tests.
