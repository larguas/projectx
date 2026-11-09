# Protocole d'acquisition EMG/IMU — version 1.0

- **Statut** : ⚠️ **hypothèse de départ, à valider par le spike 06b.**
  Les capacités réelles du capteur n'ont pas encore été mesurées (capteur non connecté
  au démarrage de la session — voir `documentation/acquisition-protocol/SENSOR_FINDINGS.md`).
  En cas d'écart entre ce document et les constats du spike, **le spike prime** et ce
  fichier est mis à jour avant la feature 07.
- **Schéma machine-readable** : [`block.schema.json`](./block.schema.json) (JSON Schema 2020-12).
- **Consommateur** : feature 07 (`backend/docs/07-ingestion.md`).

## 1. Principe

Le client (module PC, mobile ou import) regroupe les échantillons en **blocs**
(≈ 100–500 ms de données, selon la fréquence d'acquisition et le transport) et les
envoie au backend par `POST /api/v1/sessions/{id}/data/`. Le backend valide, stocke
en segments bruts et accuse réception. Chaque bloc porte un numéro de séquence qui
permet de détecter les trous et d'assurer l'idempotence.

## 2. Décisions structurantes (figées pour la v1.0)

| Décision | Choix | Raison |
|---|---|---|
| `data_type` par bloc | **Un seul `data_type` par bloc** | Aligné sur le modèle `DataBlock` (contrainte unique `(session, device, data_type, sequence_number)`), les segments de stockage (un segment par `(session, device, data_type)`) et la détection de trous par flux. Un bloc mixte rendrait ambiguë la numérotation des séquences. |
| EMG et IMU | **Blocs séparés** (`data_type` distincts : `emg_*` d'un côté, `imu_*` de l'autre) | Fréquences d'échantillonnage généralement différentes ; nature de signal différente (le pipeline 08 ne doit pas appliquer les mêmes traitements aux deux) ; segmentation et stats d'ingestion par `(device, data_type)`. L'alignement temporel EMG↔IMU se fait sur `acquisition_timestamp` + la synchronisation d'horloge de la feature 07. |
| Horodatage | **Trois horodatages distincts** : `acquisition_timestamp` (début du bloc, horloge appareil/client, UTC), `client_sent_at` (envoi, horloge client, UTC), `received_at` (ajouté par le serveur) | La spec exige de distinguer réception et acquisition ; la synchronisation EMG/IMU multi-appareils en dépend. Les timestamps individuels d'échantillons restent optionnels (`sample_timestamps`). |
| Transport | **JSON avec `Content-Encoding: gzip` accepté et recommandé.** Format binaire compact **seulement si le spike 06b montre que le JSON ne suffit pas** (débit effectif Q1/Q2, pertes Q9) — à définir alors comme `Content-Type: application/x-emg-block`. | Critère explicite de `07-ingestion.md` : ne pas complexifier sans mesure. À trancher après les enregistrements du spike. |
| Déclaration des pertes | Champ optionnel `dropped_samples` (entier ≥ 0, déclaré par le client) | Le client connaît les pertes capteur→client (trous de séquence Q7/Q9) ; il les déclare plutôt que de laisser le serveur deviner. |

## 3. Structure d'un bloc

Tous les champs marqués **obligatoire** sont exigés par `block.schema.json`.
Le statut « confirmé / à valider » renvoie aux questions du spike 06b.

| Champ | Type | Obligatoire | Description | Statut |
|---|---|---|---|---|
| `protocol_version` | string | oui | Version du protocole, ex. `"1.0"`. Le client envoie aussi l'en-tête `X-Protocol-Version`. | confirmé (contrat backend) |
| `session_id` | string | oui | Identifiant de la séance. | confirmé (contrat backend) |
| `device_id` | string | oui | Identifiant du capteur/appareil. | confirmé (contrat backend) |
| `sequence_number` | integer ≥ 0 | oui | Numéro de séquence du bloc, **par `(device, data_type)`**, strictement croissant, sans trou idéal. Idempotence : même séquence + même contenu = doublon accepté ; même séquence + contenu différent = `409`. | confirmé (contrat backend) ; existence d'un compteur côté capteur à valider (Q7) — sinon le client génère la séquence depuis les paquets reçus. |
| `acquisition_timestamp` | string (UTC ISO-8601) | oui | Début du bloc, horloge de l'appareil/client. | confirmé ; dérive d'horloge réelle à valider (Q8). |
| `client_sent_at` | string (UTC ISO-8601) | oui | Instant d'envoi par le client (estimation du décalage d'horloge serveur). | confirmé (contrat backend) |
| `sample_rate` | number > 0 | oui | Fréquence d'échantillonnage en Hz. | à valider : valeur réelle et stabilité (Q2). |
| `data_type` | string (enum) | oui | Type de signal : `emg_raw`, `emg_rectified`, `emg_envelope`, `imu_accel`, `imu_gyro`. Extensible par évolution de protocole. | à valider : nature réelle du signal (Q4) — le capteur peut ne produire qu'un sous-ensemble. |
| `channels` | array d'objets | oui (≥ 1) | Un objet par canal : `channel_id` (string), `units` (string), `samples` (array de nombres, même longueur pour tous les canaux du bloc). | à valider : nombre de canaux et format de paquet capteur (Q3), unités/résolution (Q5). |
| `calibration` | object (JSON) | non | Informations de calibration figées (gain, offset, échelle µV ou valeurs brutes…). | à valider : ce que le capteur expose réellement (Q5/Q10). |
| `metadata` | object (JSON) | non | `source` (`pc_agent`/`mobile`/`import`), `connection_type` (`ble`/`usb`/`serial`/…), `device_model`, `client_version`. | à valider : connexion réelle et modèle (Q1/Q10). |
| `sample_timestamps` | array de nombres (ms) | non | Timestamps individuels d'échantillons, si le capteur les expose par échantillon. | à valider (Q6) — sinon absent et reconstruction côté client depuis `acquisition_timestamp` + `sample_rate`. |
| `dropped_samples` | integer ≥ 0 | non | Échantillons perdus entre le capteur et le client, déclarés par ce dernier. | à valider : détection des pertes possible ? (Q7/Q9). |

**Ajouté par le serveur** (jamais envoyé par le client) : `received_at` (UTC ISO-8601).

### Exemple (structure indicative, valeurs fictives)

```json
{
  "protocol_version": "1.0",
  "session_id": "ses_01J...",
  "device_id": "dev_emg_01",
  "sequence_number": 42,
  "acquisition_timestamp": "2026-11-09T18:30:00.000Z",
  "client_sent_at": "2026-11-09T18:30:00.150Z",
  "sample_rate": 1000,
  "data_type": "emg_raw",
  "channels": [
    { "channel_id": "ch_01", "units": "raw", "samples": [120, 125, 132, 118, 110] }
  ],
  "calibration": { "gain": 1000, "offset_uV": 0 },
  "metadata": {
    "source": "pc_agent",
    "connection_type": "ble",
    "device_model": "prototype_v1",
    "client_version": "0.3.0"
  }
}
```

## 4. Limites et versions

- **Limites configurables côté serveur** (exposées par `GET /api/v1/protocol/`) :
  taille maximale d'un bloc, nombre maximal d'échantillons par bloc, nombre maximal de
  blocs par requête. Valeurs définitives à calibrer pendant la feature 07 (test de charge).
- **Versions** : `PROTOCOL_MIN_SUPPORTED`, `PROTOCOL_DEPRECATED`, `PROTOCOL_CURRENT`
  côté serveur ; en-têtes clients `X-Protocol-Version`, `X-Client-Version`,
  `X-Client-Type`. Sous le minimum → `426 Upgrade Required`.
- **Politique de dépréciation** : une version de protocole restera supportée au moins
  **un cycle de release majeur** après son remplacement (durée minimale), avec en-têtes
  `Deprecation`/`Sunset` et avertissement dans le corps pendant cette période. Le schéma
  est strict (`additionalProperties: false`) : un nouveau champ optionnel impose une
  **mineure** (ex. `1.0` → `1.1`) avec mise à jour de `block.schema.json` ; un changement
  de sémantique ou une suppression de champ impose une nouvelle **majeure**.

## 5. Points en attente du spike 06b

Avant de coder la feature 07, compléter depuis `SENSOR_FINDINGS.md` :

1. **Q1** → valeur réelle de `metadata.connection_type` et débit effectif (impact sur la
   taille de bloc recommandée).
2. **Q2/Q3** → `sample_rate` nominal réel, nombre de canaux, format de paquet capteur
   (exemples d'offsets de séquence/timestamp à documenter ici).
3. **Q4/Q5** → sous-ensemble réel de `data_type`, `units` et contenu minimal de `calibration`.
4. **Q6/Q7** → présence réelle de `sample_timestamps` et du compteur capteur ; sinon le
   client génère `sequence_number` et reconstruit les timestamps (le documenter ici).
5. **Q8/Q9** → justifier ou non le format binaire (`application/x-emg-block`) et fixer la
   tolérance de synchronisation d'horloge.
