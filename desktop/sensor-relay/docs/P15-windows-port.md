# P15 — Port Windows (à faire plus tard)

## Objectif
Faire tourner le module sur Windows sans réécrire le cœur : seuls `platform/`, les adaptateurs et le packaging changent. Si le garde-fou de P01 a été respecté, le travail est limité.

## Pré-requis
P14 terminée, module stable sur macOS.

## Périmètre
Implémentation Windows de `platform/`, BLE et série sous Windows, packaging et signature, CI.

## Tâches

### Couche plateforme (`platform/windows.py`)
- [ ] Empêcher la veille : `SetThreadExecutionState`.
- [ ] Démarrage automatique : clé `HKCU\…\Run` ou Planificateur de tâches.
- [ ] Notifications (ex. `winotify`), ouverture d'URL, statut Bluetooth.
- [ ] Barre système : implémentation `TrayIcon` avec `pystray` (attention aux threads).
- [ ] Chemins (`%APPDATA%`, `%LOCALAPPDATA%`) via `platformdirs` ; Gestionnaire d'identifiants Windows via `keyring`.

### Capteurs
- [ ] BLE : `bleak` (WinRT) — adresse MAC disponible, appairage et alimentation différents de macOS ; vérifier les contextes de threads (STA/MTA) en présence d'une UI ; relancer la checklist matériel de P10.
- [ ] Série : ports `COMx`, pilotes FTDI/CP210x/CH340 ; les tests par `openpty` ne s'appliquent pas → port virtuel (com0com) ou tests sautés avec marqueur.

### Packaging
- [ ] PyInstaller sous Windows, installateur (Inno Setup ou MSIX), **signature de code** (certificat ou service de signature) pour éviter SmartScreen ; vérifier les faux positifs antivirus.
- [ ] Mises à jour/`upgrade_url` identiques à macOS.

### CI et tests
- [ ] Ajouter `windows-latest` à la matrice CI ; adapter les tests dépendant de POSIX.
- [ ] Checklist manuelle sur un PC Windows propre (installation, Bluetooth, séance réelle, démarrage automatique, désinstallation).

## Critères d'acceptation
- Même suite de tests de contrat et même scénario de séance qu'en macOS.
- Installateur signé fonctionnel sur un PC Windows propre.
- `make check` passe sur macOS, Linux et Windows.
