# Validation réelle — banc Docker isolé, chapitres 2 et 3

28 octobre 2026. **VERIFIED sur le périmètre synthétique décrit ici** ; choix du
moteur et ingestion automatisée de production restent **PARTIAL / BLOCKED**.
Branche `feat/todo-phases-0-3`, base `d9180f6`, sans commit/push/merge de ce lot.
Aucune section TODO depuis `3.1 models.dev` modifiée.

## Campagne et objets conservés

Autorisation explicite : deux nouveaux conteneurs sur VM150, images déjà locales,
données synthétiques et destinations temporaires. Série finale du **28/10/2026
18:31:31 au 18:32:12, Europe/Paris** (`17:31:31–17:32:12Z`).

- Racine VM : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03`.
- Série retenue : `attempt-20261028T173131Z-7490ca`, code `code-v6`.
- Conteneurs : suffixes `-postgresql` et `-surrealdb` de ce nom de campagne ;
  les deux sont **arrêtés, code 0**. Réseau suffixe `-net`, interne, conservé.
- Données, bases partiellement chargées, exports, dumps, anciennes versions et
  erreurs sont conservés sur la VM. **Aucune suppression automatique**.
- Les deux POC historiques sont restés arrêtés. Leurs identités, images, états,
  dates de démarrage/arrêt et montages sont identiques avant/après. Aucun SELECT,
  démarrage, import ou changement de schéma dans ces POC ; les 405 modèles
  historiques n’ont pas été recomptés pendant cette campagne.

Le [manifeste de revue](results/20261028-vm150-isolated-session/review-manifest.json)
contient IDs, configuration publique, index des fichiers et SHA256. Source bundle :
`56e47701f958a6c4b00d486c76275fcf613c64d6a606921e76ca9a52caf4e693`.
Archive de revue `review-v6.tgz` :
`f6b048bc966dcc9e63118a548c5cfa184dd7ed641c27a810550820ebe9d67f28`.
Les 45 fichiers référencés et leur taille ont été contrôlés après transfert.
Les credentials du banc restent hors Git dans un fichier privé ; le mot de passe
SSH et les JWT ne sont dans aucun artefact de revue. Aucun token HTTP enregistré.

## Versions, ressources et confinement appliqués

| Élément | PostgreSQL | SurrealDB |
|---|---|---|
| Version réellement interrogée | 16.15, Alpine/x86_64 | 3.3.4 |
| ID image local utilisé | `sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab` | `sha256:649a60a3b9c0177d9923c938e1c2563e48cde2a9d06ac2c0519714be719b02af` |
| CPU / RAM / PID | 2 CPU / 4 Gio / 256 | 2 CPU / 4 Gio / 256 |
| Utilisateur conteneur | 70:70 | 1000:1000 |
| Réglage mémoire principal | shared_buffers 128 Mio, work_mem 16 Mio | cache RocksDB 128 Mio, buffers 32 Mio × 2 |

`--pull=never`, IDs exacts, aucun téléchargement. Pas de port publié, réseau
interne, rootfs en lecture seule, `cap-drop ALL`, `no-new-privileges`, aucun GPU,
device, socket Docker ou mode privilégié dans les conteneurs. Tmpfs bornés pour
les fichiers temporaires ; données dans deux nouveaux bind mounts de campagne.
L’image SurrealDB crée aussi un **nouveau volume anonyme `/logs`** : son identité
et sa date sont vérifiées, sa taille incluse dans le budget et le volume conservé.
Il ne s’agit pas du volume `/logs` historique.

Préflight : environ 30 Gio de RAM et 167 Gio de disque disponibles sous `/var/tmp`.
Surveillance toutes les deux secondes : cgroups v2, CPU, mémoire, PID, tailles
apparentes, espace hôte et nouveaux messages noyau matériels/OOM ciblés. Seuils
d’arrêt : 3,5 Gio par conteneur, 224 PID, 2 Gio de données par moteur, 6 Gio pour
la campagne, moins de 8 Gio de RAM ou 10 Gio de disque hôte disponibles. Aucun
seuil déclenché ni OOM/erreur matérielle surveillée dans la série finale.

| Mesure de la série finale | PostgreSQL | SurrealDB |
|---|---:|---:|
| Pic mémoire cgroup | 157,01 Mio | 625,25 Mio |
| CPU, delta entre premier/dernier échantillons | 5,064 s | 24,334 s |
| Maximum de PID observé | 9 | 30 |
| Données cumulées, taille apparente maximale | 369,98 Mio | 169,06 Mio |

La mémoire cgroup inclut les caches ; ce n’est pas du RSS processus. Le CPU
échantillonné n’inclut pas nécessairement les dernières fractions de seconde.
Les tailles cumulent aussi les essais précédents conservés : **ne pas les utiliser
comme comparaison de stockage d’un seul dataset**. Pic campagne 698 303 650 octets ;
mémoire hôte disponible minimale 30 366,39 Mio. Ce n’est pas un stress test prolongé.

## Corpus, requêtes et métriques distinctes

Paliers successifs **30 → 1 000 → 10 000** ; passage au suivant uniquement après
parité, plans validés, restauration et contrôle des ressources. Pour N modèles :
N variantes, N benchmarks, huit providers, deux rôles/runtimes/GPU, N relations
`supports`, puis 50/1 625/16 250 relations `fits`. Liens natifs typés SurrealDB et
jointures avec clés étrangères PostgreSQL. Aucune donnée de catalogue personnel.

Huit requêtes : filtre provider ; modèle/base/quantification ; provider/coût ;
runtime/GPU ; rôle candidat ; benchmark local ; cosinus exact ; hybride exact.
Vecteurs déterministes de 16 dimensions, top 10 et égalités ordonnées par ID.
Hybride = 0,75 × cosinus + 0,25 × présence littérale de `chat`, **pas BM25/ANN**.
Le générateur a une période courte et des égalités : ce corpus valide contrats et
plans, pas la qualité d’embeddings ou la diversité d’un catalogue réel.

Chaque requête est comparée à un oracle Python indépendant. Deux profils : clés
primaires/structures natives, puis index supplémentaires déclarés. Première
exécution conservée, trois échauffements, **15 répétitions warm** ; ordre PG/Su
alterné. Pas de flush des caches OS. Le p95 par rang sur 15 mesures est le maximum
de l’échantillon, pas une estimation robuste de latence de production.

Les mesures normales utilisent des connexions persistantes depuis la VM :
protocole PostgreSQL natif et HTTP SurrealDB. Le client PG normalise les réponses
par `json_agg` ; son coût figure dans la latence client. Aucun lancement Docker/CLI
dans les échantillons. Décodage JSON final non inclus dans le chronométrage réseau.
PostgreSQL utilise trust sur ce réseau fermé ; SurrealDB utilise une **session
Bearer obtenue avant les mesures**. Les protocoles/authentifications restent
différents : il s’agit de latences API observées, pas d’un classement pur moteur.
[Contrat HTTP officiel](https://surrealdb.com/docs/reference/rest-api/http-protocol).

`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` et `EXPLAIN FULL` constituent **d’autres
exécutions**, stockées dans `plan_measurement`. Leurs temps ne sont ni ajoutés
aux 15 échantillons ni utilisés pour les remplacer. Le plan PG porte sur la requête
sans l’enveloppe `json_agg`. Planning/Execution Time PG, durée d’enveloppe Surreal
et `elapsed_ns` de chaque opérateur gardent leurs unités et périmètres. Aucun
total fabriqué en additionnant les nœuds.

SurrealDB 3.3.4 renvoie un tableau d’un résultat ; `result` est un **arbre**,
avec `operator`, `context`, `metrics`, `children` optionnel et `total_rows` à la
racine. Le parseur vérifie récursivement compteurs et métriques exécutées, ainsi
que le nombre de lignes attendu. Une réponse incompatible arrête le palier.
[Fixture observée masquée](fixtures/surreal_explain_334.observed_sanitized.json) et
[tests de non-régression](../../tests/discovery/test_isolated_bench_contracts.py). Aucun repli supprimant
la validation des plans.

### Latences client finales à 10 000 modèles, après index — millisecondes

| Requête | PG p50 | PG p95 | Surreal p50 | Surreal p95 |
|---|---:|---:|---:|---:|
| Filtre provider | 0,398 | 2,944 | 4,331 | 7,205 |
| Base / quantification | 0,496 | 0,644 | 87,272 | 90,139 |
| Provider / coût | 0,276 | 0,394 | 4,917 | 5,088 |
| Runtime / GPU | 0,826 | 2,837 | 132,968 | 147,536 |
| Rôle candidat | 0,558 | 0,786 | 51,667 | 54,699 |
| Benchmark local | 0,174 | 0,307 | 10,335 | 11,512 |
| Vecteur exact | 17,174 | 19,377 | 20,688 | 24,877 |
| Hybride exact | 19,283 | 20,031 | 24,347 | 27,008 |

Les données brutes, les deux profils et chaque plan sont dans
[stage.json](results/20261028-vm150-isolated-session/final/10000/stage.json).
Les requêtes Surreal de liens partent des variantes avec filtrage ; d’autres
directions de parcours/optimisations ne sont pas évaluées. Aucun résultat global
sur les graphes profonds, la concurrence ou les index ANN n’en est déduit.

## Lots UTF-8, interruptions et reprise réelle

Découpage **entre instructions complètes**, jamais dans une chaîne SQL ou un
enregistrement. Taille de la transaction complète vérifiée après encodage UTF-8,
plafond **524 288 octets**, wrappers et reçu compris. Les plans et journaux indiquent
le SHA de charge, les octets SQL et les octets du corps réellement envoyé.

| Modèles | Lots PG / max octets | Lots Surreal / max octets |
|---|---:|---:|
| 30 | 3 / 15 503 | 29 / 18 864 |
| 1 000 | 2 / 518 333 | 19 / 504 355 |
| 10 000 | 15 / 521 416 | 189 / 510 807 |

Chaque lot et son reçu sont dans une même transaction. Chaque réponse SQL est
contrôlée, puis le reçu est relu en base **avant** de poursuivre. La reprise exige
un préfixe exact de reçus conformes au manifeste ; trou, hash différent ou reçu
absent font échouer la livraison.

À 30 modèles, dans les deux moteurs : interruption après le premier lot confirmé,
fermeture/reconnexion du client, vérification du préfixe persistant, échec injecté
dans le deuxième lot avec rollback intégral, puis reprise. PG saute un lot et en
applique deux ; Surreal en saute un et en applique 28. Rejeu complet : **zéro lot
appliqué**, contenu et cardinalités inchangés, aucune instruction perdue/dupliquée.
Il s’agit d’un arrêt contrôlé du livrateur entre lots, pas d’une panne physique.

Les temps d’import observés à 1k/10k sont respectivement 157,6/1 329,8 ms pour PG,
265,0/2 443,1 ms pour Surreal. Ils incluent transactions, confirmations et journaux,
avec des granularités de lots différentes. À 30, les fautes/reconnexions sont aussi
incluses : ce palier qualifie la reprise et ne classe pas le débit d’import.

## Restaurations et Discovery Cache B2/B3

**Huit restaurations** vers de nouvelles destinations : deux moteurs × trois
tailles, plus deux restaurations du Discovery Cache. Dumps/exports conservés sur
la VM ; SHA et tailles dans les artefacts de revue. Pour chaque taille, empreintes
logiques avant/après identiques sur les neuf tables de charge et les reçus de lots,
y compris liens natifs. Aucun restore sur une base source ou historique.

Sur le cache B2 : sept sources normalisées depuis leurs fixtures, cinq types de
ressources distincts, réimport idempotent, changement de révision **synthétique**
sans changement de clé, champs inconnus et `null`/`false`/zéro/liste vide conservés.
Observation partielle : une ressource non observée est gardée. Deux ressources
portant le même nom/identifiant synthétique sur deux plateformes restent distinctes.
Comparaison de scopes incompatibles refusée. Table témoin étrangère au cache
préservée dans les seules bases d’essai. Cache final **9 ressources** restaurées à
l’identique dans chaque moteur. Aucune révision fournisseur réellement sondée.

Échec PG avant COMMIT : rollback ; déconnexion TCP pendant une transaction :
rollback. Échec Surreal `/import` : **422, première instruction conservée** ;
rejeu idempotent validé. Les lots SQL transactionnels ci-dessus et le `/import`
legacy ont donc des garanties différentes. Voir
[résultat Discovery](results/20261028-vm150-isolated-session/final/discovery/discovery_qualification.json).

**Limite confirmée : les générateurs B2 legacy acceptent un ancien snapshot qui
peut remplacer une révision plus récente.** Le test négatif l’a reproduit sur les
données synthétiques puis rétabli l’état attendu. La précondition de payload
erronée est bien rejetée par des requêtes CAS de test dans les deux moteurs,
mais aucun exécuteur CAS/staging de production n’est livré. Les générateurs
historiques et identités B2 restent inchangés ; le plan d’import général reste
non exécutable. Cela bloque la clôture de l’ingestion automatisée protégée.

## Historique des essais et décisions restantes

Essais conservés : v1 refusait l’arbre EXPLAIN ; v2 redéfinissait le namespace ;
v3 envoyait 6 908 395 octets sur `/sql` (BrokenPipe observé, charge supérieure à
sa limite documentée) ; v4 arrêté pour revue demandée du parseur et des lots.
v5 a validé tous les tests, mais ses latences avec Basic par requête ne sont pas
mélangées à la série finale v6 avec session préalable. Les
[résultats v5](results/20261028-vm150-isolated/review-manifest.json) sont conservés.
Les erreurs et tentatives restent dans les manifests et journaux, sans sélection
des échantillons les plus rapides.

Le protocole à cinq requêtes de `comparison_workload.py` reste un prototype
distinct et compatible ; il ne parse pas automatiquement ces rapports à huit
requêtes. Les anciens contrats/snapshots B2/B3 et leurs références ne changent pas.

Recommandation **à valider** : PostgreSQL est le candidat de départ pour cette
charge relationnelle, compte tenu des résultats API et du coût CPU observés.
Ce n’est pas une décision d’adoption, ni une conclusion universelle de performance.
La licence exacte SurrealDB et les usages futurs restent dans le
[rapport de décision conditionnelle](COMPARISON_PHASE2.md). Aucun moteur choisi
automatiquement, aucune migration ou suppression.

Restent ouverts : choix du moteur/licence d’exploitation ; ANN, vecteurs réalistes,
caches froids, concurrence et parcours de graphe alternatifs ; ordonnancement et
collecte fournisseur ; révisions distantes, fraîcheur, domaines/comptes ; exécuteur
d’import protégé. Pas d’installation de scheduler. Proxmox, HAOS, NAS, GPU et pilote
OS restent hors autorisation. Arrêt strict avant le chapitre 3.1.
