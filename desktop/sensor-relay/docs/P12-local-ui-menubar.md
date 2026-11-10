# P12 — Interface locale et barre de menus macOS

## Objectif
Permettre à un coach non technique d'utiliser le module sans terminal : se connecter, choisir le sportif et le capteur, enregistrer, voir l'état.

## Périmètre
UI web locale servie par le daemon, icône de barre de menus, notifications, i18n fr/en.

## Hors périmètre
Packaging (P14), analyses (restent dans l'application web).

## Choix (par défaut, modifiable)
- **UI locale** : application React + Vite + TypeScript + Tailwind (même stack que le frontend), construite en fichiers statiques embarqués dans le package, servie sur `http://127.0.0.1:<port>/ui`, parlant uniquement à l'API locale (P09). Alternative plus légère : pages servies par Python avec htmx. Sans logique métier côté UI.
- **Barre de menus** : abstraction `platform/tray.py` (`TrayIcon`) ; implémentation macOS avec `rumps` (ou pyobjc). Sous macOS la boucle de la barre de menus occupe le **thread principal** : le cœur asyncio tourne dans un thread d'arrière-plan. `emg-agent app` lance barre de menus + daemon. Implémentation Windows plus tard (P15).

## Écrans
1. **Connexion** : affiche le code, ouvre le navigateur, attend l'approbation.
2. **Accueil** : état serveur, capteur, file d'envoi, séances à synchroniser.
3. **Capteurs** : scan, connexion, état, qualité du signal en direct.
4. **Nouvelle séance** (assistant) : sportif → placement (« même que la dernière fois ? ») → capteurs/canaux → type (entraînement/calibration) → contrôle préalable.
5. **Enregistrement** : chronomètre, signal décimé par canal (WebSocket `live`), indicateurs (pertes, saturation, qualité), file d'envoi, boutons de marqueurs, arrêt.
6. **Fin** : progression du vidage, confirmation, lien « ouvrir dans l'application web ».
7. **Réglages** : serveur, durée des blocs, limites du spool, démarrage à l'ouverture de session, langue.
8. **Diagnostic** : export du paquet de diagnostic (P13).

## Barre de menus et notifications
- Icône à états (gris : hors ligne/inactif, vert : OK, orange : attention, rouge : erreur), séance en cours, « Ouvrir », « Démarrer/Arrêter », « Quitter ».
- Notifications macOS : capteur perdu, envoi bloqué, séance terminée, mise à jour requise (`platform.notify`).

## Tâches
- [ ] Projet UI (`desktop/sensor-relay-ui/`), build statique intégré au package (`make build-ui`).
- [ ] Écrans 1 à 8, états de chargement/erreur, mode sombre, i18n fr/en.
- [ ] Courbe en direct (décimation côté serveur, canvas/uPlot) fluide à 8 canaux.
- [ ] `platform/tray.py` + implémentation macOS (`rumps`) + commande `emg-agent app`.
- [ ] Notifications.

## Tests
- Tests unitaires UI (Vitest / Testing Library).
- **E2E Playwright** contre le daemon avec capteur simulé + faux backend : parcours complet connexion → séance → arrêt → fin.
- Logique de la barre de menus testée via l'interface `TrayIcon` simulée ; checklist manuelle macOS (icône, menu, notifications).
- Accessibilité de base (clavier, contrastes).

## Critères d'acceptation
- Un coach réalise une séance simulée sans toucher à la CLI.
- `make check` passe (incluant lint et tests de l'UI).
