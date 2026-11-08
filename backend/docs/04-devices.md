# Feature 04 — Devices : capteurs

## Objectif
Enregistrer et gérer les capteurs, indépendamment du fabricant.

## Périmètre
CRUD des appareils, association à un propriétaire, catalogue de modèles et capacités.

## Hors périmètre
Communication avec les capteurs (module PC / mobile), réception des données (feature 07).

## Modèles
- `devices.DeviceModel` : `manufacturer`, `name`, `protocol_version`, `connection_types` (liste : `ble`, `usb`, `serial`), `capabilities` (JSON : canaux EMG max, IMU oui/non, `sample_rates` supportés, résolution), catalogue géré en admin.
- `devices.Device` : `owner` (user), `device_model` (FK), `serial_number`, `name`, `firmware_version`, `status` (`active`/`retired`), `last_seen_at`, `calibration_defaults` (JSON), unique `(device_model, serial_number)`.

## Endpoints
- `GET/POST /api/v1/devices/`
- `GET/PATCH/DELETE /api/v1/devices/{id}/` (DELETE = désactivation logique)
- `GET /api/v1/device-models/` (lecture seule pour les utilisateurs)

## Tâches
- [ ] App `devices`, modèles, migrations.
- [ ] Un utilisateur voit ses appareils ; un coach voit ceux de ses sportifs uniquement avec le scope `devices:read` (utiliser `core.access` de la feature 03).
- [ ] Contrôle du `serial_number` dupliqué (message d'erreur clair).
- [ ] Service `touch_device(device)` pour mettre à jour `last_seen_at` (utilisé par l'ingestion).
- [ ] Seed du catalogue : un modèle `prototype_v1` via fixture ou migration de données.
- [ ] Admin Django pour `DeviceModel`.

## Tests
- CRUD, doublon de serial, isolation entre utilisateurs, accès coach avec/sans scope, désactivation logique.

## Critères d'acceptation
- Un utilisateur peut enregistrer un capteur `prototype_v1` et le retrouver.
- `make check` passe.
