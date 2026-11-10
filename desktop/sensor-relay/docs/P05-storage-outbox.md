# P05 — Stockage local : outbox SQLite

## Objectif
Ne jamais perdre un bloc : le persister avant tout envoi, le conserver jusqu'à confirmation, et reprendre exactement après un crash ou une coupure Internet.

## Périmètre
Base SQLite, API d'outbox, compteurs de séquence persistants, quotas, reprise au démarrage.

## Hors périmètre
Envoi réseau (P07), logique de séance (P08).

## Stockage
- Fichier `agent.db` dans le dossier de données, mode WAL, accès via un thread/exécuteur dédié (jamais bloquant dans asyncio), migrations par `PRAGMA user_version`.
- Tables : `local_sessions` (id local, id serveur, athlète, état, dates), `sequence_counters` (session, appareil, type, prochaine séquence), `outbox` (id, session, appareil, type, séquence, `payload` gzip, `n_samples`, `status` = `pending|inflight|acked|rejected`, tentatives, dernière erreur, dates), `annotations_outbox`, `kv`.

## API `OutboxStore`
`enqueue(block)` — **atomique** : bloc + incrément du compteur dans la même transaction (pas de trou ni doublon de séquence après crash) · `claim_batch(session, max_blocks, max_bytes)` (ordre par séquence) · `mark_acked(seqs)` · `mark_rejected(seq, reason)` · `release_inflight()` au démarrage · `pending_stats()` · `purge_acked(session)` (appelée seulement après vérification de fin de séance, voir P07/P08) · `size_bytes()`. Implémente aussi `SequenceStore` (P02) et `BlockSink` (P04).

## Quotas et robustesse
- Plafond `spool_max_mb` (défaut 2 Go) et âge maximal ; alerte à 80 %. À 100 % : **ne jamais jeter de blocs** ; refuser de démarrer une séance et, en cours de séance, arrêter proprement avec une erreur claire.
- Contrôle d'espace disque avant de démarrer.
- Au démarrage : repérer les séances avec blocs non envoyés (« séances à synchroniser »).
- Les fichiers de données sont créés en 0600 dans un dossier 0700.

## Tâches
- [ ] Schéma, migrations, accès thread-safe.
- [ ] `OutboxStore` complet, branché sur `RecordingPipeline` (remplace le sink de test).
- [ ] Reprise après crash (`release_inflight`, compteurs cohérents).
- [ ] Quotas, alertes, espace disque.
- [ ] Commande `emg-agent outbox` (stats, séances à synchroniser).

## Tests
- Atomicité : interruption simulée entre bloc et compteur → aucune incohérence.
- Ordre, `claim/ack/reject`, reprise des `inflight`.
- Redémarrage au milieu d'une séance : la séquence reprend sans trou ni doublon.
- Quota atteint : comportement sans perte.
- Débit : ≥ 500 blocs/s en `enqueue` sur Mac récent (mesuré, documenté).
- Concurrence producteur/consommateur.

## Critères d'acceptation
- Tuer le processus (`kill -9`) pendant un enregistrement simulé, relancer : tous les blocs persistés sont retrouvés, séquences continues.
- `make check` passe.
