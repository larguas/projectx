# P03 — Interface capteur, Device Manager et capteur simulé

## Objectif
Définir le contrat unique que tout capteur respecte, et fournir un capteur simulé/replay pour développer tout le module **sans matériel**.

## Périmètre
Interface d'adaptateur, types communs, Device Manager (détection, connexion, reconnexion), adaptateurs `ReplayAdapter` et `SyntheticAdapter`, suite de tests de contrat.

## Hors périmètre
BLE et série réels (P10, P11), pipeline (P04).

## Interfaces (`adapters/`)
- `types.py` : `SensorDescriptor` (identifiant de découverte, nom, transport), `SensorInfo` (code du modèle, numéro de série, firmware, canaux), `ChannelSpec` (id capteur, `data_type`, unités, `sample_rate`, résolution, échelle), `SampleFrame` (valeurs par canal, `device_counter` optionnel, `device_timestamp` optionnel, `host_monotonic_ns`), `AdapterEvent` (connecté, déconnecté, erreur, batterie…).
- `base.py` : `SensorAdapter` (ABC asynchrone) : `discover()`, `connect(descriptor)`, `disconnect()`, `info()`, `stream()` (itérateur asynchrone de `SampleFrame`), `events()`. Contrat : `stream()` se termine proprement à la déconnexion ; aucune exception non typée ne s'échappe (`AdapterError`, `AdapterDisconnected`).
- `devices/manager.py` : `DeviceManager` — registre des adaptateurs, scan global, connexion, **reconnexion automatique** avec backoff plafonné et événements d'état ; plusieurs capteurs connectés en parallèle.

## Adaptateurs de test
- `replay.py` : rejoue un fichier enregistré (npz/CSV du spike, ou fixture) en temps réel ou accéléré. Options déterministes (graine) : perte de paquets, doublons, désordre, jitter, déconnexion à t = X, redémarrage du compteur (wraparound).
- `synthetic.py` : EMG synthétique (bruit + salves d'activation) et IMU simulé avec répétitions ; N canaux, taux configurable.
- Fixtures de données dans `tests/data/` (échantillon réel anonymisé du spike dès qu'il existe, sinon généré).

## Tâches
- [ ] Types et ABC, exceptions typées.
- [ ] `DeviceManager` avec politique de reconnexion testable (horloge injectable).
- [ ] `ReplayAdapter` et `SyntheticAdapter` avec injection de fautes.
- [ ] `tests/adapters/contract.py` : suite de tests que **tout** adaptateur doit passer (découverte, connexion, flux, déconnexion propre, erreurs typées). Réutilisée en P10/P11.
- [ ] Commande `emg-agent sensors scan --adapter synthetic` (démonstration).

## Tests
- Suite de contrat sur Replay et Synthetic.
- Injection de pertes/doublons/désordre : les frames portent les compteurs attendus.
- Reconnexion : backoff respecté, arrêt après annulation, événements émis.
- Deux capteurs simultanés.

## Critères d'acceptation
- Un flux de `SampleFrame` réaliste est disponible sans matériel, avec fautes injectables.
- `make check` passe.
