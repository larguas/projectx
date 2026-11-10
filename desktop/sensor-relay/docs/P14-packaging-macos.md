# P14 — Packaging macOS : application installable

## Objectif
Un `.app` (dans un `.dmg`) qu'un coach installe par glisser-déposer, sans avertissement de sécurité, qui demande les autorisations au bon moment et peut démarrer à l'ouverture de session.

## Pré-requis
P12 terminée. **Compte Apple Developer Program** (certificat « Developer ID Application » + identifiants de notarisation) : sans lui, l'appli fonctionne en local mais macOS affichera des avertissements (Gatekeeper).

## Périmètre
Build de l'app, signature, notarisation, DMG, démarrage automatique, première ouverture, information de mise à jour, processus de release.

## Hors périmètre
Mise à jour automatique (Sparkle) — plus tard ; Windows (P15).

## Tâches
- [ ] **Build** : PyInstaller (cohérent avec Windows ensuite) → `emg-agent.app` ; `make build-macos`. Inclure l'UI statique, le schéma de protocole embarqué, les profils capteurs, les dépendances natives (bleak/pyobjc).
- [ ] **Info.plist** : identifiant de bundle (variable, nom du produit non figé), version issue de `pyproject.toml` (= `CLIENT_VERSION`), `LSUIElement` (application de barre de menus, sans icône dans le Dock), `NSBluetoothAlwaysUsageDescription` (texte clair en français/anglais).
- [ ] **Entitlements** minimaux pour le *hardened runtime* (accès Bluetooth, et uniquement les exceptions de bibliothèques Python strictement nécessaires — à valider par test).
- [ ] **Signature et notarisation** : `codesign` (Developer ID, hardened runtime), `xcrun notarytool submit --wait`, `stapler`, scripts `make sign` / `make notarize`, secrets par variables d'environnement.
- [ ] **DMG** (`create-dmg` ou équivalent) avec raccourci Applications.
- [ ] **Démarrage automatique** : `platform/macos.py` — LaunchAgent (`~/Library/LaunchAgents/<bundle-id>.plist`) activable/désactivable depuis les réglages (P12).
- [ ] **Première ouverture** : écran d'accueil expliquant les autorisations (Bluetooth, notifications, accès au Trousseau) avant de les déclencher.
- [ ] **Architectures** : Apple Silicon d'abord ; Intel en build séparé (universal2 non garanti avec numpy/pyobjc) — documenter le choix.
- [ ] **Information de mise à jour** : au démarrage et sur `426`, afficher « mise à jour disponible/requise » avec `upgrade_url` ; pas d'installation automatique.
- [ ] **CI de release** : workflow sur étiquette `agent-v*` (build, signature, notarisation, artefact DMG), certificat et identifiants en secrets GitHub.
- [ ] Documentation `documentation/desktop/release.md` : procédure de release, versions, désinstallation (emplacement des données, logs, LaunchAgent, éléments du Trousseau).

## Tests
- Smoke test de l'app construite : démarre, `status` répond, UI accessible.
- Vérifications automatiques : `codesign --verify --deep --strict`, `spctl --assess`, `stapler validate`.
- **Checklist manuelle sur un Mac « propre »** (autre session utilisateur ou machine vierge) : ouverture sans avertissement, invite Bluetooth, connexion, séance simulée puis réelle, redémarrage avec démarrage automatique, désinstallation.

## Critères d'acceptation
- Le `.dmg` installé sur un Mac neuf s'ouvre sans avertissement et réalise une séance avec le vrai capteur.
- `make check` passe ; la CI produit un artefact signé et notarisé.
