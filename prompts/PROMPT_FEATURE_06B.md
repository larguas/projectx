Tu continues le développement de la plateforme EMG (backend Django 5.x + DRF,
géré par uv). Les features 01 « Socle projet », 02 « Accounts », 03 « Sportifs,
coachs, équipes et partage de données », 04 « Devices », 05 « Exercices,
muscles, entraînements », 05b « Setups de placement et calibrations » et
06 « Séances » sont terminées et commitées ; le repo est propre et
`make check` passe.

Ta tâche : mener la feature 06b — Spike capteur réel — en suivant strictement
backend/docs/06b-hardware-spike.md (script de lecture du capteur, enregistrements
de référence, script d'analyse, constats écrits, alignement du protocole).
Attention : c'est un spike matériel, pas une feature Django. Elle doit être
finie avant la feature 07 (ingestion), car le protocole y est figé sur la base
de tes constats.

Avant de coder, lis dans cet ordre :
1. backend/AGENT.md — conventions générales du repo (le code du spike reste
   versionné et lisible comme le reste)
2. backend/docs/00-index.md — décisions applicables ici (notamment n°4 : un
   seul format de blocs versionné, validé sur le vrai capteur avant d'être
   figé ; n°5 : idempotence par `sequence_number` ; n°13 : versions de
   protocole/client vérifiées par le backend)
3. specs/software.md §4 et §5 — architecture d'acquisition et protocole
   supposé (hypothèse de départ, PAS la vérité terrain)
4. backend/docs/07-ingestion.md — ce que la feature 07 attend du spike
   (section « Protocole » : champs, transport, limites configurables) ; son
   pré-requis est explicite : en cas d'écart, le spike prime et ce fichier
   doit être mis à jour avant de coder l'ingestion
5. backend/docs/06b-hardware-spike.md — les 11 questions à trancher, tâches,
   critères d'acceptation

Points d'attention :
- Séparation des rôles (c'est écrit dans le doc) : toi tu écris les scripts et
  la structure des constats (`documentation/acquisition-protocol/SENSOR_FINDINGS.md`,
  à créer) ; l'utilisateur réalise les mesures physiques avec le capteur. JAMAIS de valeur inventée : chaque réponse aux 11 questions doit
  provenir d'une mesure réelle ou être marquée « inconnu » avec la raison. Si
  le capteur n'est pas branché ou détectable au démarrage, livre la phase 1
  (scripts + squelette des constats) et arrête-toi avec une checklist claire
  « à faire avec le capteur » — ne bloque pas, ne devine pas.
- Environnement jetable : `scripts/sensor_spike/` est un mini-projet uv
  indépendant (son propre pyproject.toml + uv.lock ; dépendances `bleak` et/ou
  `pyserial` selon le matériel, plus `numpy` pour l'analyse). Ne pollue PAS
  l'environnement du backend. Détermine d'abord la connexion réelle (USB,
  série ou BLE — c'est la question n°1) via `lsusb` et/ou un scan bleak, puis
  choisis les dépendances et documente le choix.
- Le lecteur doit horodater chaque enregistrement côté hôte (timestamp de
  réception + timestamp capteur si exposé) et écrire un fichier brut lisible a
  posteriori : c'est ce qui permet de calculer jitter, dérive d'horloge et
  pertes de séquence après coup.
- Script d'analyse rapide avec au minimum quatre métriques : débit réel
  (échantillons/s observés vs nominaux), jitter (variabilité des inter-arrivées),
  pertes de séquence (trous dans le compteur/numéro de séquence), dérive
  d'horloge sur 10 min et 30 min.
- `shared/protocol/` n'existe pas encore dans le repo : crée `PROTOCOL.md` et
  `block.schema.json` (JSON Schema, `protocol_version: "1.0"`) en partant du
  protocole supposé (specs/software.md §5 + backend/docs/07-ingestion.md
  section « Protocole »), puis aligne-les sur les constats réels : champs
  réellement disponibles, encodage retenu (JSON gzip seul, ou binaire en plus
  uniquement si les mesures le justifient), taille de bloc recommandée, gestion
  des timestamps. La feature 07 reprendra ces fichiers tels quels.
- Décisions à trancher et documenter dans PROTOCOL.md : un seul `data_type` par
  bloc ou plusieurs ; flux EMG et IMU dans le même bloc ou séparés.
- Échantillon de référence : committer un petit fichier ANONYMISÉ (aucun
  identifiant utilisateur, séance ou appareil personnel) dans
  `backend/tests/data/` (CSV ou npz — décide et documente le format),
  utilisable tel quel par les features 08 et 09.
- Mettre à jour backend/docs/07-ingestion.md avec les décisions prises et les
  écarts par rapport au protocole supposé (le spike prime, c'est son pré-requis).

Règles de travail :
- Une session = une feature : uniquement la 06b, dans l'ordre des tâches du doc.
- uv pour les dépendances du spike (pas de pip/requirements.txt) ; `uv run`
  depuis le dossier du mini-projet.
- Coche les tâches dans backend/docs/06b-hardware-spike.md au fur et à mesure.
- Pas de code Django attendu : si tu modifies quoi que ce soit sous backend/
  (outre les fichiers de données), `make check` doit continuer à passer en fin
  de session.
- Petits commits Conventional Commits (`chore(spike): ...`, `docs(protocol): ...`).
- En fin de session, les critères d'acceptation du doc sont remplis :
  SENSOR_FINDINGS.md répond aux 11 questions (mesurées ou « inconnu » + raison),
  le protocole 1.0 est aligné sur les capacités réelles du capteur, un fichier
  d'exemple réel est disponible pour les tests.
- Termine par un court rapport : réponses aux 11 questions, décisions prises,
  écarts avec le protocole supposé, points ouverts avant la feature 07.

Pièges connus des sessions précédentes (à éviter) :
- Les fichiers de backend/docs/ sont en lecture seule localement (mode 444) :
  `chmod u+w`, éditer, puis restaurer le mode 444 (sinon diff de mode git).
- Le binaire `python` nu n'est pas sur le PATH : toujours `uv run python ...`
  ou l'interpréteur du venv concerné.
- Si tu ajoutes des fonctions réutilisables dans le spike (parsing, calculs de
  métriques), garde-les pures et testables ; pas de dépendance à Django.

Spécificités de la machine (déjà vérifiées) :
- Le capteur physique est mis à disposition par l'utilisateur ; commence par
  la détection du matériel (`lsusb`, scan BLE) et documente ce que tu observes
  avant d'écrire le lecteur.
- L'infra backend tourne déjà (emg-postgres + emg-redis sur 127.0.0.1:5432/6379)
  — cette feature ne la touche pas ; NE PAS TOUCHER le conteneur `vela_db_prod`.
