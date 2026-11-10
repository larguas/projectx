# P08 — Orchestration d'une séance

## Objectif
Dérouler le scénario du spec §12.2 : choisir le sportif, le placement et le capteur, démarrer, enregistrer, terminer proprement, y compris après un crash ou une coupure.

## Pré-requis backend
Features 03 (scopes), 04 (appareils), 05b (setups), 06 (séances, annotations). Avant la 07 : faux backend étendu.

## Périmètre
Machine à états locale, préparation, contrôle préalable, enregistrement, fin de séance, reprise, calibration, marqueurs, bus d'événements.

## Hors périmètre
API locale/CLI (P09), UI (P12).

## États (`sessions/controller.py`)
```text
idle → preparing → ready → recording → stopping → flushing → completing → done
                              ↓                                   ↑
                        needs_attention ───────────────────────────┘
failed / cancelled depuis n'importe quel état actif
```
Persistés dans `local_sessions` (P05).

## Préparation
- Sportif : liste via le backend ; vérifier le scope `sessions:write` (message clair sinon : « demande l'autorisation au sportif »).
- Placement : `suggested-setup` (« même placement que la dernière fois ? »), ou création d'un setup `simple` ; sans setup, la séance reste possible (`setup_not_declared`, avertissement affiché).
- Capteurs : chaque capteur connecté est rattaché à un `Device` du backend par numéro de série (création si absent, modèle via `device-models`).
- Mappage canaux capteur ↔ canaux du setup, validé ; `session_type` = `training`/`calibration`/`test` (+ `calibration_type`).
- **Contrôle préalable** : capteur connecté, qualité OK pendant ~3 s (pas de signal plat/saturé, pertes sous seuil), jeton valide, version de protocole acceptée, réseau disponible, espace disque, décalage d'horloge acceptable.

## Enregistrement et fin
- Création de séance + `PUT channels/devices` + `start`, puis démarrage du pipeline (P04) → outbox → uploader (P07).
- Empêcher la veille de la machine pendant l'enregistrement (`platform.prevent_sleep`).
- Capteur déconnecté : la séance continue, reconnexion automatique, trou enregistré ; au-delà d'un délai configurable → `needs_attention` (attendre, arrêter et terminer, annuler).
- Arrêt : stopper le flux, vider le buffer, **attendre l'envoi et l'accusé de tous les blocs** (progression exposée), vérifier `GET /ingestion/`, puis `complete`, puis purge (P07). Si le réseau manque : état `completing` persisté, reprise automatique. Au délai maximal : proposer « attendre », « terminer en arrière-plan », « forcer la fin (perte déclarée) », « annuler ».
- Séance annulée/terminée depuis le web (`409`) : arrêt propre et message.

## Reprise après crash
Au démarrage, lister les séances locales en `recording`/`flushing`/`completing` : proposer de reprendre la synchronisation puis de terminer (le flux capteur interrompu ne reprend pas la même séance).

## Marqueurs et calibration
- `add_marker(kind, text)` : `set_start`, `set_end`, `rep_start`, `rep_end`, `note`, `artifact`, `sync_pulse` ; `offset_ms` calculé avec l'horloge d'acquisition de l'appareil principal ; envoyés via une file d'annotations avec les mêmes garanties de reprise.
- Séances de calibration guidées, définies par des données (pas codées en dur) : repos N s ; MVC = X répétitions de T s avec repos ; pose automatique des marqueurs `set_start/set_end`. Le module **ne calcule pas** la MVC (backend feature 09).
- Plusieurs capteurs : rôle `primary`/`secondary`, marqueur `sync_pulse`.

## Bus d'événements
`events.py` : événements typés (état, qualité, sensor, upload, alerte) consommés par l'API locale (P09).

## Tâches
- [ ] Machine à états persistée et testable (horloge injectable).
- [ ] Préparation (sportif, setup, appareils, mappage) et contrôle préalable.
- [ ] Enregistrement, déconnexions, arrêt avec vidage vérifié, `complete`.
- [ ] Reprise après crash et mode `completing` hors ligne.
- [ ] Marqueurs, file d'annotations, calibration guidée.
- [ ] Bus d'événements typé.

## Tests
- Transitions valides/invalides ; scénarios complets avec capteur simulé + faux backend.
- `kill -9` pendant l'enregistrement puis reprise ; réseau coupé à l'arrêt ; capteur déconnecté 10 s puis 5 min.
- Scope manquant, setup absent, calibration, plusieurs capteurs, offsets des marqueurs.
- `complete` jamais appelé avant l'accusé du dernier bloc.

## Critères d'acceptation
- Une séance simulée de bout en bout apparaît côté (faux) backend, complète, sans trou non déclaré.
- `make check` passe.
