# Protection des imports B2 contre le rejeu ancien — 28 octobre 2026

**IMPLEMENTED / TESTED / VERIFIED sur bases synthétiques isolées** pour le SQL
nouvellement généré. Le service Discovery de production reste **PARTIAL**.
Les références B3.3, clés, empreintes, snapshots et schémas historiques sont
inchangés. Les adaptateurs et leurs transports ne sont pas modifiés.

## Contrat appliqué lors de l’écriture

`emit_discovery_import.py` conserve ses deux API et sa CLI de génération sans
connexion DB. Il émet désormais des contrôles transactionnels, sans option de
repli vers les anciennes écritures non protégées :

| État de la ressource déjà stockée | Observation entrante | Résultat |
|---|---|---|
| Absente | Valide | Insertion |
| Présente | Capture strictement plus récente | Mise à jour |
| Présente | Même instant et même contenu/snapshot | Rejeu idempotent |
| Présente | Capture plus ancienne, même payload ou autre révision | Refus, transaction annulée |
| Présente | Même instant mais contenu/snapshot différent | Refus, transaction annulée |
| Non observée dans ce snapshot | Sans instruction | Conservation |

Les dates sont comparées comme instants avec fuseau, jamais lexicalement.
La représentation JSON de `captured_at` et son exclusion de `snapshot_id`
restent inchangées. Le contrôle d’égalité inclut les métadonnées inconnues.
À instant égal, des scopes différents produisant des `last_seen_snapshot`
différents sont refusés conservativement, même pour un payload identique.

PostgreSQL : `COPY` dans une table temporaire, isolation `READ COMMITTED`,
verrou `SHARE ROW EXCLUSIVE`, contrôle de toutes les lignes existantes puis
upsert et commit dans une seule transaction. Le verrou évite la fenêtre entre
lecture de l’état et écriture, y compris pour les clés absentes ; il sérialise
les écrivains et peut réduire la concurrence. Utiliser `psql -X -v ON_ERROR_STOP=1`.
[Sémantique officielle du verrou PostgreSQL 16](https://www.postgresql.org/docs/16/sql-lock.html).

SurrealDB : `OPTION IMPORT`, transaction explicite, définition conditionnelle
de la seule table `discovery_cache`, contrôles et upserts, puis commit. Une
table existante garde sa configuration ; une ligne dépourvue d’horodatage
convertible échoue au lieu de contourner la garde. Le corps complet est limité
à **524 288 octets UTF-8** ; un dépassement refuse la génération sans sortie
partielle. Aucun découpage au milieu d’une instruction ou abandon de transaction.
Les grands snapshots nécessiteront un protocole de publication par lots distinct.
[Transactions](https://surrealdb.com/docs/reference/query-language/statements/begin),
[THROW](https://surrealdb.com/docs/reference/query-language/statements/throw),
[dates typées](https://surrealdb.com/docs/reference/query-language/language-primitives/data-types/datetimes).
Ces documentations évoluent ; la preuve exacte 3.3.4 ci-dessous est distincte.

## Qualification réelle distincte des benchmarks

Mode explicite `isolated_docker_bench.py --qualification-only --execute` :
aucun palier 30/1 000/10 000 ni nouvelle mesure de performance. Les résultats
du banc v6 restent intacts. Sources exclusivement sur fixtures, sept ressources
au départ, neuf ressources finales avec inconnues, relations et types distincts.

Série finale : `attempt-20261028T204333Z-a15681`, **21:43:33–21:43:36 Europe/Paris**.
PostgreSQL **16.15** et SurrealDB **3.3.4**, mêmes images exactes et limites que
le [banc initial](ISOLATED_DOCKER_BENCH.md). Nouvelles destinations synthétiques
et deux restaurations supplémentaires, aucune restauration historique.

| Cas | PostgreSQL | SurrealDB | Vérification de l’état |
|---|---|---|---|
| Rejeu de l’ancienne révision | `psql` exit 3 | HTTP 422, message de garde | Toutes les lignes inchangées |
| Ancienne date, payload identique | exit 3 | HTTP 422 | Aucun recul de `last_seen_at` |
| Conflit au même instant avec une nouvelle ligne | exit 3 | HTTP 422 | Aucun ajout résiduel, transaction annulée |
| Date équivalente avec `+02:00`, puis retour UTC | Succès | Succès | Rejeu idempotent |
| Restauration vers deux nouvelles destinations | Succès | Succès | Contenu exact, neuf ressources |

Échecs préalables conservés : `attempt-20261028T204033Z-e34907` et
`attempt-20261028T204222Z-f7c9c5`. La seconde réponse révèle `NotFound/Table` :
SurrealDB 3.3.4 refuse de sélectionner une table absente, ce que l’ancien UPSERT
seul ne rencontrait pas. `DEFINE TABLE IF NOT EXISTS` dans la transaction corrige
ce premier import. Le diagnostic JSON borné est conservé, sans en-têtes ni secrets.
Les trois essais terminent les conteneurs du banc ; métadonnées des POC historiques
inchangées, aucun accès SQL à ces POC, aucun accès Proxmox.

Preuves locales : [manifeste et empreintes des 24 fichiers](results/20261028-vm150-replay-guard/review-manifest.json),
[résultat final](results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/result.json).
VM : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/` ; code
`code-guard-784f0d068754/database/poc`, bundle `bundle-guard-784f0d068754.tgz`,
SHA256 `bba7cb7bafadb8ae1880ec14f495a20a396232793eb6171396812faae4861126`.
Archive `review-replay-guard-784f0d068754.tgz`, SHA256
`8998708b4c6f12ab36b41fbfd38510b0cec646d636743752dc853b5610e1c9ce`.
Les dumps restent sur VM, leurs tailles/empreintes sont dans le résultat.

## Limites à conserver avant production

- Les **anciens fichiers SQL** et anciens bundles ne sont pas protégés
  rétroactivement. Les conserver ; régénérer vers de nouveaux fichiers et revoir.
  Ne jamais changer la date d’une ancienne observation pour forcer son passage.
- La date est celle déclarée dans B2 ; ce contrôle ne prouve ni l’horloge,
  ni une révision fournisseur, ni la provenance. Un payload ancien réhorodaté
  peut encore passer. Le chemin brut reste distinct de la provenance contrôlée B4.5.
- Garde **par ressource**, sans ordre global de scope. Les clés B2 n’incluent pas
  comptes/domaines ; la garde n’autorise aucun import privé ou multi-compte dans
  une table commune. Aucune politique nouvelle d’identités ou de fusion.
- Le plan `incremental_import_plan` reste non exécutable. Son champ
  `legacy_generators_guarded=false` concerne ses préconditions CAS complètes,
  pas la nouvelle garde de capture. Même distinction pour le probe CAS conservé
  dans le rapport ; le résultat `regenerated_sql_replay_guard` qualifie la correction.
- Les erreurs, interruptions, rejouements séquentiels et restaurations ont des
  preuves réelles ; la concurrence entre transactions n’a pas été exercée dans
  cette qualification. Le protocole attendu-state/CAS général reste à livrer.
- Aucune planification, collecte fournisseur, inférence, activation worker ou
  migration/adoption DB. Pas de suppression automatique ni nettoyage des essais.

Tests : `test_discovery_replay_guard.py` vérifie génération, transaction, contrôle
UTF-8, dates, absence de mutation/suppression et intégrité des preuves réelles.
Les tests historiques ne sont pas modifiés ; les deux séries de benchmarks et
leurs manifestes sont vérifiés séparément par les tests existants.

Complément de reprise : [intégrité et CAS explicite](INTEGRITY_CAS_PHASE3.md).
Le SQL peut désormais être généré avec une baseline attendue ; sa concurrence
est qualifiée dans une série synthétique distincte. Les limites de la série
historique ci-dessus restent conservées et le chemin brut n’active pas le CAS.
