# P13 — Surveillance, diagnostics et robustesse

## Objectif
Détecter les problèmes tôt, pouvoir les diagnostiquer chez un utilisateur, et prouver la fiabilité par des tests de robustesse (spec §13.4 et §14.3).

## Périmètre
Métriques, journaux, paquet de diagnostic, chien de garde, tests « soak » avec pannes, budget de performance.

## Hors périmètre
Télémétrie produit/analytique d'usage.

## Tâches

### Métriques (`monitoring/`)
- [ ] Registre de compteurs/jauges : trames, blocs formatés/envoyés/acquittés, octets, échantillons perdus par cause, reconnexions capteur, échecs d'envoi, profondeur d'outbox, latence d'envoi p50/p95, décalage d'horloge. Exposé dans `status` (P09).

### Diagnostic
- [ ] `emg-agent diagnostics export` : archive avec logs récents, configuration **sans secrets**, instantané de statut, versions, sortie de `doctor`, statistiques d'outbox (sans contenu). **Jamais** d'échantillons ni de jetons (test automatisé de contenu).
- [ ] Sentry **optionnel et désactivé par défaut** (opt-in explicite), avec masquage des champs sensibles.

### Chien de garde
- [ ] Détection : plus de trames pendant X s alors que le capteur est connecté, uploader bloqué, disque presque plein, horloge très décalée → événements d'alerte (UI, notification).
- [ ] Veille/réveil du Mac : à la reprise, reconnexion du capteur, re-vérification réseau, trou consigné.

### Robustesse
- [ ] `tests/soak/` + `make soak` : 1 h simulée (accélérée) avec pannes aléatoires — coupures réseau, `5xx`/`429`, déconnexions capteur, `kill -9` + redémarrage. Vérifie : aucun doublon de séquence, aucun trou non déclaré, outbox vide à la fin, statistiques serveur cohérentes.
- [ ] Budget de performance : CPU et mémoire pour 8 canaux EMG à 1 kHz + IMU 100 Hz, mesurés sur un Mac Apple Silicon, consignés dans `documentation/`.
- [ ] Suite de contrôle manuelle documentée : veille/réveil, changement de réseau Wi-Fi, batterie faible du capteur.

## Tests
- Contenu du paquet de diagnostic (aucun secret/échantillon).
- Chaque règle du chien de garde avec horloge injectable.
- `soak` (marqueur dédié, nocturne optionnel en CI).

## Critères d'acceptation
- `make soak` passe de façon répétable.
- Un utilisateur peut envoyer un paquet de diagnostic exploitable sans fuite de données.
- `make check` passe.
