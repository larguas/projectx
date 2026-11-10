# P04 — Pipeline d'acquisition : Collector, Validator, Buffer, Formatter

## Objectif
Transformer le flux de `SampleFrame` en blocs conformes au protocole, en détectant et déclarant toute perte.

## Périmètre
Les quatre composants du spec §4.2 et leur assemblage (`RecordingPipeline`).

## Hors périmètre
Persistance (P05), envoi (P07), orchestration de séance (P08).

## Composants
- **Collector** (`collector/collector.py`) : consomme `stream()`, horodate la réception (`host_monotonic_ns`), alimente une file bornée. Contre-pression : si l'aval sature, **compter et signaler** (jamais de perte silencieuse), événement critique.
- **Validator** (`collector/validator.py`) : contrôles légers en continu — trous/doublons/désordre de compteur (avec gestion du **bouclage**), NaN/infini, saturation, signal plat, fréquence réelle vs déclarée (fenêtre glissante). Produit des `ValidationEvent` et un `QualityReport` en direct (pertes %, saturation, bruit estimé par canal).
- **Buffer** (`buffer/buffer.py`) : regroupe par `(device, data_type)` en blocs de `block_duration_ms` (100–500 ms, configurable) ou taille max ; gère des fréquences différentes (EMG vs IMU) ; **ferme le bloc** à chaque trou/déconnexion et rouvre avec le bon timestamp ; vidage à l'arrêt.
- **Formatter** (`buffer/formatter.py`) : construit le `Block` (P02) : mappage canal capteur → `channel_id` backend, unités, calibration, métadonnées (`source=pc`, `connection_type`, `device_model`, `client_version`), `sequence_number`, `dropped_samples`. Laisse `client_sent_at` vide : il est posé à l'envoi (P07).
- **Pipeline** (`pipeline.py`) : `RecordingPipeline.start/stop`, sortie vers une interface `BlockSink` (en P04 : mémoire / fichier JSONL pour les tests ; l'outbox arrive en P05).

## Tâches
- [ ] Collector avec file bornée, compteurs de débordement, événements.
- [ ] Validator : détection de pertes (compteur capteur, sinon écart de temps), bouclage de compteur, doublons, désordre, saturation, signal plat, fréquence mesurée.
- [ ] Buffer : durée/taille, multi-flux, fermeture de bloc sur trou, vidage final.
- [ ] Formatter : mappage de canaux configurable, `dropped_samples`, validation contre le schéma (P02).
- [ ] `QualityReport` consultable en direct (utilisé par le contrôle préalable en P08 et l'UI en P12).
- [ ] Métriques : trames reçues, blocs produits, échantillons perdus par cause.

## Tests
- Scénarios Replay avec pertes/doublons/désordre/bouclage : `dropped_samples` exact.
- **Propriété** : concaténation des échantillons des blocs = entrée moins pertes déclarées ; timestamps continus sauf trous déclarés.
- Déconnexion en milieu de bloc : bloc fermé, nouveau bloc avec le bon timestamp.
- Contre-pression : aucune perte silencieuse (événement + compteur).
- Multi-fréquences EMG 1 kHz + IMU 100 Hz.
- Tous les blocs produits valident le schéma partagé.

## Critères d'acceptation
- Avec le capteur simulé et pertes injectées, la sortie est exacte et toute perte est comptée.
- `make check` passe.
