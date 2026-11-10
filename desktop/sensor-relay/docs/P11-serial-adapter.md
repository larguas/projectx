# P11 — Adaptateur USB / port série (conditionnel)

## Objectif
Supporter un capteur filaire (USB ou série) via le même contrat d'adaptateur. **À faire seulement si** `SENSOR_FINDINGS.md` indique un lien USB/série, ou pour un futur capteur.

## Périmètre
Adaptateur `pyserial`, découverte des ports, décodage de trames robuste, hot-unplug.

## Hors périmètre
Windows (P15).

## Tâches
- [ ] `adapters/serial.py` : lecture dans un thread dédié → file bornée → asyncio ; paramètres (débit, parité…) pris dans le profil du capteur.
- [ ] Découverte par `serial.tools.list_ports` avec filtres VID/PID du profil ; **sous macOS utiliser les ports `/dev/cu.*`** (pas `/dev/tty.*`), pour les puces FTDI, CP210x, CH340 ; documenter les pilotes éventuels (notamment sur Apple Silicon).
- [ ] Décodage des trames d'après le protocole du capteur (entête de synchro, longueur, CRC/COBS/SLIP selon les constats) : **resynchronisation** après octets corrompus, comptage des trames invalides.
- [ ] Détection du débranchement à chaud et reconnexion via le Device Manager.
- [ ] Profil + parser purs, comme en P10 (réutiliser l'agencement `adapters/profiles/`).
- [ ] Commandes `sensors scan|info|dump` fonctionnant avec ce transport.

## Tests
- Suite de contrat de P03.
- Port série virtuel (`os.openpty`) simulant le capteur : trames valides, corrompues, coupées, débit élevé, débranchement.
- Parser sur enregistrements réels ; robustesse sur octets aléatoires.
- `hardware` : branchement/débranchement réels.

## Critères d'acceptation
- Un flux série de 10 min est lu sans perte non comptée, resynchronisation vérifiée.
- `make check` passe.
