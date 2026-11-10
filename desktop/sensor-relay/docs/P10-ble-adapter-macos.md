# P10 — Adaptateur BLE (macOS) et profil du capteur

## Objectif
Lire le vrai capteur en Bluetooth Low Energy depuis un Mac et alimenter le pipeline, avec le profil du capteur séparé du code.

## Pré-requis
`documentation/acquisition-protocol/SENSOR_FINDINGS.md` (spike 06b) et fichier d'exemple réel. Si le spike dit « USB/série » plutôt que BLE : faire P11 à la place.

## Périmètre
Adaptateur `bleak`, parser pur, profil du capteur, commandes `sensors` réelles, tests matériel, notes macOS.

## Hors périmètre
Windows (P15), USB/série (P11).

## Structure
- `adapters/profiles/<modele>.toml` : UUID de service/caractéristiques, nom d'annonce, agencement des canaux, taux d'échantillonnage, résolution, échelle de conversion, unités, présence de compteur/timestamp.
- `adapters/<modele>/parser.py` : fonction **pure** `bytes → [SampleFrame]` (sans I/O), avec gestion du bouclage du compteur.
- `adapters/ble.py` : transport `bleak` — scan filtré, connexion avec délai, découverte des services, abonnement aux notifications, lecture du service Device Information (série, firmware), événements de déconnexion. Ajouter un capteur = un profil + un parser + éventuellement un transport.

## Tâches
- [ ] Profil du capteur d'après `SENSOR_FINDINGS.md`.
- [ ] Parser pur testé sur les enregistrements réels du spike (+ test de robustesse sur paquets tronqués/aléatoires).
- [ ] Adaptateur BLE passant la suite de contrat de P03 (avec un faux client `bleak` pour la CI).
- [ ] Horodatage : utiliser compteur/timestamp du capteur si disponibles ; sinon horloge d'acquisition (P02), jamais l'heure d'arrivée seule.
- [ ] Reconnexion : intégration avec le Device Manager (P03) ; reprise du flux sans doublon.
- [ ] Commandes réelles : `sensors scan`, `sensors info`, `sensors dump --seconds 30 --out fichier.npz` (enregistrement local brut **sans backend**, remplace le script du spike).
- [ ] `doctor` : état Bluetooth, permission, avertissements ci-dessous.
- [ ] Mesurer et documenter dans `documentation/acquisition-protocol/SENSOR_RELAY_BLE_NOTES.md` : débit réel, pertes, reconnexion.

## Spécificités macOS (à traiter explicitement)
- **Permission Bluetooth** : l'application qui lance Python (Terminal, iTerm, VS Code…) doit être autorisée dans *Réglages Système → Confidentialité et sécurité → Bluetooth*. Sans cela le scan ne trouve rien ou le processus peut s'arrêter brutalement. `doctor` et les messages d'erreur doivent l'expliquer. Pour l'app empaquetée : clé `NSBluetoothAlwaysUsageDescription` (P14).
- **Pas d'adresse MAC** : CoreBluetooth donne un UUID propre à chaque Mac. Identifier un capteur par son **numéro de série** (service Device Information ou annonce), jamais par l'adresse ; mémoriser localement la correspondance UUID ↔ série.
- Pas de contrôle de la taille de MTU ni des intervalles de connexion côté Mac : s'adapter aux valeurs négociées et les consigner.
- Bluetooth désactivé, capteur hors de portée, mise en veille/réveil du Mac : états gérés et événements explicites.

## Tests
- Suite de contrat + parser sur données réelles.
- Faux `bleak` : déconnexion en plein flux, notifications dupliquées, compteur qui boucle.
- **Matériel** (`hardware`, checklist manuelle) : 10 min continues, éloignement jusqu'à déconnexion puis retour, Bluetooth coupé/réactivé, veille/réveil du Mac.

## Critères d'acceptation
- `emg-agent sensors dump --seconds 600` produit un fichier cohérent, pertes comptées, sans plantage.
- Après déconnexion volontaire, le flux reprend automatiquement.
- `make check` passe.
