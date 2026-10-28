# Checkpoint durable — phases 0 à 3 générales — 2026-10-28T18:44:40+01:00

**Instruction prioritaire : arrêt des nouvelles campagnes/tests/développements, préservation.**
Aucun artefact supprimé. Aucun push, merge ou commit. Les deux conteneurs du banc sont arrêtés, code 0 ; les POC historiques sont restés arrêtés. Ne pas reprendre une campagne ou un développement sans nouvelle instruction utilisateur.

## 1. État exact de la TODO et limite de périmètre
- Branche `feat/todo-phases-0-3`, base/HEAD `d9180f6baefff1cbe500e3d263ec18c9f407382d`.
- Limite stricte : AVANT `## 3.1 models.dev`. Ne pas commencer 3.1 ni les chapitres suivants.
- Snapshot verbatim de toute la TODO dans le périmètre : [TODO_PHASES_0_3_20261028.snapshot.txt](TODO_PHASES_0_3_20261028.snapshot.txt), 470 lignes.
- SHA256 du préfixe : `3ffbf9c3b8dd3b6d292b335961acc0c45fa4e354fb8f78086fc49fd2138b0b7d`.
- SHA256 du suffixe 3.1+ : `52cb52ee4afce412e6306f60e0fe38752dd4c52dc67fa115dd5ce872b283fe34` ; identique à HEAD.
- 49 cases initialement ouvertes (phase 0 : 0 ; phase 1 : 38 ; phase 2 : 9 ; phase 3 générale : 2).
- Premier lot local : neuf lignes closes (six GPU, doublon VFIO, volumes persistants, ajout des healthchecks).
- Banc réel : cinq lignes de phase 2 supplémentaires closes. **35 restent ouvertes : phase 1 = 29, phase 2 = 4, phase 3 générale = 2.**
- Les lignes composites/doublons ne représentent pas nécessairement 35 lots autonomes.

Les cinq clôtures de ce banc, VERIFIED sur synthétique : comparaison requêtes/index/mesures ; requêtes représentatives ; vecteur/hybride exacts 16 dimensions ; liens typés/graphe ; Docker/consommation mémoire. Les healthchecks historiques avant arrêt ont réussi ; disponibilité courante des POC arrêtés non validée.

Toutes les cases encore ouvertes, texte exact et lignes actuelles de TODO.md :

| Ligne | Case ouverte |
|---:|---|
| 115 | - [ ] Créer la VM via le script Proxmox |
| 126 | - [ ] Définir sauvegarde de la VM |
| 138 | - [ ] Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables. |
| 139 | - [ ] Confirmer la disponibilité courante des healthchecks des deux bases après autorisation : cinq dernières sondes de chaque base réussies avant l’arrêt, mais conteneurs actuellement arrêtés ; aucun démarrage autorisé. |
| 182 | - [ ] Étendre les sondes à plusieurs modèles et formats ; vérifier les révisions, fichiers, relations et éventuelles restrictions d'accès. L'API sondée ne fournit pas de SHA Git exploitable. |
| 192 | - [ ] Étendre les sondes à d'autres dépôts et étudier séparément les ressources datasets, spaces, MCP, skills et les modèles servis par l'AI Gateway. |
| 202 | - [ ] Synchroniser les fichiers locaux non suivis de la VM avec la branche publiée, après comparaison ; voir [la procédure ciblée](database/poc/MOARK_VM_SYNC.md). |
| 203 | - [ ] Étudier séparément capacités, quotas applicables et dépôts de poids MoArk/Gitee ; aucune association automatique par nom. |
| 215 | - [ ] Décider la sémantique future des accès/visibilités, de l'isolation domaines/comptes, des révisions et des collectes partielles avant toute évolution de format ou d'identité. |
| 231 | - [ ] Décider et tester la politique de redirections B1 avant sa migration ; préserver le cas NIM 404 et les limites du SDK. Voir [TRANSPORT_B42.md](database/poc/TRANSPORT_B42.md). |
| 239 | - [ ] Examiner le prototype et décider multitag NIM, namespaces domaines/comptes, provenance synthétique/réelle et conventions de collecte partielle avant un registre opérationnel. |
| 248 | - [ ] Examiner le registre manuel avant toute extension online ; provenance synthétique/réelle, domaines/comptes, NIM multitag et résultats partiels restent à décider. |
| 258 | - [ ] Décider la provenance obligatoire et le contrat d'import avant toute protection complète du B2 brut ; l'option ne remplace pas une validation d'origine. |
| 268 | - [ ] Définir l'enrôlement/rotation/révocation des émetteurs et la CLI protégée ; HMAC local ne prouve pas une collecte distante. |
| 269 | - [ ] Raccorder les reçus HTTP conditionnels au moteur budgété, la reprise inter-sources et les politiques de fraîcheur avant de déclarer B4.5 opérationnel. |
| 270 | - [ ] Définir pagination distante, garanties/quotas SDK, concurrence par hôte et budget global dans des lots séparés ; aucun scheduler. |
| 279 | - [ ] Valider les contrats d'identité/appairage/bail et l'API de mission avant B5.1 ; développer un faux worker puis autoriser séparément un pilote Linux CPU. |
| 280 | - [ ] Choisir langage/packaging, stockage durable et politique de clés ; vérifier licences/artefacts exacts, notamment Desktop avant toute redistribution. |
| 281 | - [ ] Établir une matrice réellement testée par OS/runtime ; aucune capacité GPU/inférence/agent annoncée comme vérifiée par cette étude. |
| 282 | - [ ] Garder interfaces tierces, VM automatisée, compagnon multi-OS et USB dans des lots séparés ; aucune installation/provisionnement/migration effectués dans B5.0. |
| 294 | - [ ] Finaliser la pile HTTP de production et l'isolation OS d'un vrai worker ; les contrôles locaux HTTP/identité/sauvegarde sont validés au checkpoint B5.2, sans exposition LAN. |
| 295 | - [ ] Définir les contrats agents/rôles/baux réels, appairage/TLS et politiques multi-utilisateurs avant une ouverture LAN ou exécution d'outils ; aucune installation, inférence ou collecte réelle dans B5.1. |
| 307 | - [ ] Avant un vrai worker : isolation OS éprouvée, politiques réseau/outils/enfants, PKI/appairage/TLS et pile HTTP de production ; conserver le prototype sans IA réelle ni découverte LAN. |
| 317 | - [ ] Autoriser puis exécuter les tests négatifs OS sur une machine distincte : UID/groupes, secrets/SQLite/objets inaccessibles, FS, réseau, GPU/Docker, CPU/RAM/PID, runtime et arrêt des enfants — **NOT VERIFIED**. |
| 318 | - [ ] Qualifier le producteur indépendant de permis et fermer/vérifier le réseau OS au port backend ; contrats, observations et canal de refus ajoutés en B5.3.1, sans activation. `--application-test` ne valide pas l'isolation, le filtre IP candidat seul autorise tous les ports loopback. |
| 319 | - [ ] Avant une inférence ou un outil réel : contrat de lecture des versions d'entrée, quotas cumulés I/O/calcul, politique des moteurs/outils, preuves OS et profils Windows/macOS distincts ; conserver AnythingLLM/Open WebUI facultatifs. |
| 329 | - [ ] Autoriser un pilote négatif sur une **VM jetable distincte** selon [le plan opérateur Debian](docs/architecture/B53_DEBIAN13_VALIDATION.md), avec confirmations séparées pour comptes, fichiers, unités et pare-feu. Aucun accès à la VM historique autorisé. |
| 330 | - [ ] Qualifier collecte indépendante, compte exclusif, code/FD/montages, règles/IPv4/IPv6/ports et ressources/arrêt avant un producteur de permis positif. Le contrôleur livré émet toujours `deny` ; strict reste bloqué, OS **NOT VERIFIED**. |
| 331 | - [ ] Définir si nécessaire une attestation serveur distincte : aucun champ worker ne promeut aujourd'hui le statut `verified`. Pas de vraie inférence, modèle, GPU ou service privilégié permanent. |
| 353 | - [ ] Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation). |
| 365 | - [ ] Vérifier précisément les contraintes de licence de SurrealDB avant adoption |
| 366 | - [ ] Décider du moteur principal |
| 367 | - [ ] Documenter la décision |
| 432 | - [ ] Industrialiser l'ingestion incrémentale (exécution planifiée, reprise sur erreur, rétention, surveillance) ; le POC B2 est une importation **manuelle**, pas encore un Discovery Service en production. |
| 441 | - [ ] Éprouver les imports partiellement échoués, les changements de révision réels et les variations de périmètre ; conserver les snapshots et définir la politique de rafraîchissement. |

## 2. Terminé, partiel et bloqué — preuves

| État | Réalisation / limite | Preuve |
|---|---|---|
| VERIFIED | Paliers 30 → 1 000 → 10 000, huit requêtes, index et plans obligatoires, connexions persistantes | `database/poc/results/20261028-vm150-isolated-session/final/{30,1000,10000}/stage.json` |
| VERIFIED | Lots entiers, UTF-8 réel ≤512 Kio avec transaction/reçu ; lecture du reçu avant suite | `confirmed_sql_batches.py`, `isolated_bench_ingestion.py`, plans et journaux de lots |
| VERIFIED | Interruption entre lots, reconnexion, échec atomique du lot suivant, reprise et rejeu sans doublon/perte dans les deux moteurs | `final/30/{postgresql,surrealdb}-batch-ingestion.json` |
| VERIFIED | Huit restaurations vers nouvelles bases, empreintes logiques identiques (charge et reçus ; cache B2) | `final/{30,1000,10000}/restore.json`, `final/discovery/discovery_qualification.json` |
| VERIFIED | B2 : sept sources, cinq types, valeurs inconnues/null/false/0/[], révision synthétique stable en identité, scopes incompatibles refusés, non-suppression, absence de fusion | `final/result.json`, snapshots synthétiques `final/discovery/` |
| VERIFIED | Cache final à neuf ressources restauré, table témoin étrangère préservée dans les seules bases temporaires | `b2_restore_new_destinations`, `unrelated_table_preserved` dans résultat Discovery |
| TESTED | Plan VM offline, VM150 protégée, refus écrasement image/snippet, correction cloud-init/disque unique ; inspecteur Docker en lecture seule | `tests/infrastructure/`, `infrastructure/proxmox/`, `inspect_poc_health.py` |
| PARTIAL | Choix DB et finalisation comparatif : recommandation conditionnelle PostgreSQL sur cette charge, pas adoption | `COMPARISON_PHASE2.md`, `ISOLATED_DOCKER_BENCH.md` |
| PARTIAL | Licence SurrealDB exacte du tag 3.3.4 étudiée ; adéquation aux usages futurs et notices de l’image pas définitivement validées | `COMPARISON_PHASE2.md` et sources officielles citées |
| PARTIAL | Ingestion générale : budgets/cache/reprise manuelle raccordés, mais pas de scheduler ni writer protégé général | `MANUAL_INCREMENTAL_RUN.md`, `incremental_import_plan.py` non exécutable |
| BLOCKED | Révisions fournisseur réelles, scopes/comptes/domaines et politique de publication/fraîcheur de production | Pas de collecte fournisseur autorisée ; décision de contrat nécessaire |
| BLOCKED | Proxmox, backup/restore VM150, script VM réel, OS worker, multi-OS, HAOS/NAS/GPU | Aucun accès supplémentaire Proxmox ni environnement OS jetable autorisé ; banc Docker ne couvre pas ces opérations |

## 3. Résultats PostgreSQL / SurrealDB — série finale v6

- Versions : `PostgreSQL 16.15 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit` ; `surrealdb-3.3.4`.
- Même VM Debian 13, images locales exactes ; aucun pull. 2 CPU / 4 Gio / 256 PID par conteneur, swap total limité à 4 Gio, rootfs RO, cap-drop ALL, no-new-privileges, utilisateurs 70:70 et 1000:1000. Réseau interne sans ports publiés, aucun GPU/socket Docker/device ajouté.
- Profils finaux : PostgreSQL natif/trust sur réseau de test fermé ; SurrealDB session Bearer établie AVANT les mesures. Aucun JWT/password dans les rapports. Profils/protocoles différents : latence API, pas classement pur des moteurs.
- Deux profils d’index (structures de base puis index supplémentaires), trois échauffements, quinze répétitions warm ; p95 par rang = maximum de ces quinze mesures. Aucun cache froid OS, ANN, concurrence ou qualité sémantique testé.
- Temps de requête séparés de `plan_measurement` : EXPLAIN constitue une autre exécution. Ne pas additionner les elapsed_ns des opérateurs. PG JSON-agg de normalisation est dans la latence client mais pas dans la requête profilée.

### Latences normales à 10 000 modèles après index, ms

| Requête | PG p50 | PG p95 | Su p50 | Su p95 |
|---|---:|---:|---:|---:|
| base_quant | 0.496 | 0.644 | 87.272 | 90.139 |
| hybrid_exact | 19.283 | 20.031 | 24.347 | 27.008 |
| local_benchmark | 0.174 | 0.307 | 10.335 | 11.512 |
| provider_cost | 0.276 | 0.394 | 4.917 | 5.088 |
| provider_filter | 0.398 | 2.944 | 4.331 | 7.205 |
| role_candidate | 0.558 | 0.786 | 51.667 | 54.699 |
| runtime_gpu | 0.826 | 2.837 | 132.968 | 147.536 |
| vector_exact | 17.174 | 19.377 | 20.688 | 24.877 |

Les index SQL/SurrealQL exacts sont conservés par taille dans `postgres-indexes.sql` et `surreal-indexes.surql`. Les plans bruts et métriques de toutes les tailles sont dans chaque `stage.json`. Les parcours Surreal testés partent des variantes avec filtrage ; optimisations/directions alternatives non évaluées.

### Ressources de la série, mesures cgroup

| Mesure | PG | Su |
|---|---:|---:|
| Pic mémoire cgroup, Mio | 157.012 | 625.254 |
| CPU delta échantillonné, s | 5.064 | 24.334 |
| PID maximum | 9.000 | 30.000 |
| Taille apparente cumulée, Mio | 369.975 | 169.063 |

- Pic campagne : 698,303,650 octets ; mémoire hôte disponible minimale 30366.39 Mio.
- Aucun OOM, seuil de ressources ou erreur matérielle noyau ciblée détecté pendant cette série. Le CPU est un delta entre échantillons, pas un comptage exact jusqu’à l’arrêt ; mémoire cgroup inclut caches. Les tailles cumulent les essais antérieurs conservés et ne comparent pas un dataset unique.
- Imports 1k/10k : PG environ 157,6/1329,8 ms ; Su 265,0/2443,1 ms. Transactions, confirmations et journaux inclus, granularités différentes. À 30, fautes/reconnexions incluses : pas un benchmark de débit.

## 4. Artefacts conservés et sécurité de reprise

- VM : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03`.
- Série finale : `attempt-20261028T173131Z-7490ca/` ; code exécuté `code-v6/` et source `bundle-v6.tgz`.
- SHA256 bundle v6 : `56e47701f958a6c4b00d486c76275fcf613c64d6a606921e76ca9a52caf4e693`.
- Sous chaque taille : `corpus.synthetic.json`, SQL de charge, index, plans/mesures, journaux de reçus, `postgres.dump`, `surreal.surql`, `restore.json`, `stage.json`.
- Sous `discovery/` : snapshots synthétiques, qualification, `discovery-postgres.dump`, `discovery-surreal.surql`.
- `objects.json` garde les deux IDs exacts et le réseau ; `events.jsonl` garde les événements de toutes les tentatives. `surreal.private.env` contient uniquement les credentials générés du banc : privé, ne pas afficher/exporter. Le mot de passe SSH ne doit pas être recopié dans un fichier.
- Tous les `code-v1` à `code-v6`, bundles et anciennes tentatives sont conservés. Aucune suppression, prune, nettoyage ou restauration historique.
- Revue VM finale : `review-v6.tgz`, `review-manifest-v6.json`. SHA archive `f6b048bc966dcc9e63118a548c5cfa184dd7ed641c27a810550820ebe9d67f28`.
- Copie locale durable sous Git NON ENCORE COMMITTÉE : `database/poc/results/20261028-vm150-isolated-session/` (46 fichiers). Version v5 provisoire Basic conservée séparément sous `.../20261028-vm150-isolated/` (45 fichiers). Ne pas mélanger ces séries.
- Originaux/bundles locaux supplémentaires sous `/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03*` ; métadonnées de travail `/tmp/pepeuch-bench-current.json`, résumés `/tmp/pepeuch-bench-session-summary.json`. La reprise doit prioriser dépôt + artefacts VM, pas dépendre de /tmp.

| Conteneur de test | ID | État |
|---|---|---|
| /pepeuch-dbbench-20261028t165804z-a8e6ef03-postgresql | `ea3bba2b497fd5160ebada8a3bc751f6a8a0ac999231d2f7a99ccebd0f4c566a` | exited, exit 0 |
| /pepeuch-dbbench-20261028t165804z-a8e6ef03-surrealdb | `b740e2d06ed8fdeba1be53eebd577b72f8235d2fdb430a2cbca838cf060c258c` | exited, exit 0 |

Montages dédiés conservés (ne pas supprimer sans GO) :
- postgresql : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/postgresql-data` → `/var/lib/postgresql/data` (bind).
- surrealdb : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/surrealdb-data` → `/data` (bind).
- surrealdb : `/var/lib/docker/volumes/23abe333b47908e1ce906f0228fe2b6480bef573c21d13d949513af7f57b7fae/_data` → `/logs` (volume).

## 5. Anomalies et limites à ne pas masquer

**Risque B2 confirmé : un ancien snapshot importé par les générateurs legacy peut remplacer une révision plus récente.** Le scénario a été reproduit dans les seules bases synthétiques, puis rétabli. Les requêtes CAS isolées refusent une empreinte incorrecte, mais aucun writer CAS/staging général n’est livré ; `incremental_import_plan` reste non exécutable. Ne pas annoncer un Discovery automatisé protégé.

- `/import` Surreal est non atomique dans le scénario : HTTP 422 et première instruction conservée. Le rejeu idempotent est testé. Les nouveaux lots SQL transactionnels avec reçus ont des garanties distinctes.
- Changements de révision utilisés : synthétiques réellement importés, pas des révisions de fournisseurs sondés. Provenance, identités B2, types, absence de fusion et non-suppression vérifiés sans collecte externe.
- v1 : parseur supposait une liste de lignes ; réponse réelle EXPLAIN FULL = arbre dans une enveloppe de résultat. Fixture observée masquée et validation récursive obligatoire ajoutées.
- v2 : namespace redéfini entre paliers ; création déplacée au niveau campagne.
- v3 : BrokenPipe avec première requête SQL de 6 908 395 octets, au-delà de la limite documentée /sql ; corrigé par lots complets bornés UTF-8.
- v4 : interruption contrôlée pour revue utilisateur ; données partielles conservées.
- v5 : tous les paliers validés, mais Basic par requête introduisait un coût non comparable à une session PG. Conserver cette série comme provisoire, sans mélanger les mesures avec v6.
- v6 : authentification Surreal hors chronométrage normal, série complète VERIFIED. Pas de claim universel moteur : profils natifs, échantillon réduit, vecteurs synthétiques périodiques, pas ANN/cold/concurrence/graphes alternatifs.
- POC historiques : seulement empreintes de métadonnées Docker inchangées, pas une nouvelle vérification d’intégrité de leurs volumes. Aucun accès supplémentaire Proxmox, HAOS, NAS, GPU ou OS négatif autorisé.

## 6. Tests, refus de relance et reprise

| Suite | Dernière preuve | État à ce checkpoint |
|---|---:|---|
| Discovery local | 339 OK, dernière opération terminée | actuel ; inclut artefacts finaux v6 |
| Worker local | 48 OK, dernière opération terminée | actuel |
| Infrastructure locale | 19 OK, dernière opération terminée | actuel, Proxmox/Docker simulés |
| Control Plane | 123 OK précédemment | relance finale NON exécutée |
| Isolation applicative | 63 OK précédemment | relance finale NON exécutée ; aucun pilote OS réel |
| Discovery sur VM150 | 339 OK avant v6 ; 332 avant v5 | code/fixtures du bundle exécuté |

**406 tests réussis dans la dernière vague achevée.** Référentiel cumulé 592 avec les 123+63 succès antérieurs, mais ne pas annoncer une nouvelle exécution complète de 592 tests. Le contrôle automatique a refusé les relances Control Plane et isolation quand la dernière instruction utilisateur a interdit de nouvelles campagnes. Aucun contournement ni nouvelle demande de relance pendant ce checkpoint.

`git diff --check` passé avant sauvegarde ; suffixe TODO 3.1+ identique à HEAD. Les anciens tests, adaptateurs, CLI Discovery, générateurs B2, schémas historiques, Control Plane et worker ne sont pas modifiés. Référence B3.3 SHA256 `ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.

### Prochaine session : lecture seule d’abord

```bash
git status --short --untracked-files=all
git branch --show-current
git rev-parse HEAD
git diff --check
cat docs/audit/CHECKPOINT_20261028_PHASES_0_3.md
cat database/poc/ISOLATED_DOCKER_BENCH.md
```

Conserver les modifications locales. Aucun commit n’a été créé ; les commits pourront être préparés après revue/validation utilisateur. Ne pas reset/clean/stash global, écraser un fichier, supprimer les résultats ou synchroniser automatiquement le dépôt VM (encore au checkpoint B5.2).

Après une NOUVELLE instruction autorisant les tests, commandes locales de reprise :

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s database/poc -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/control_plane -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/worker -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/isolation -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/infrastructure -p 'test_*.py' -q
```

Loopback/SO_PASSCRED et contrôles de permissions infrastructure nécessitaient une exécution hors sandbox sous l’UID courant, pas en root. Les relances actuellement refusées demandent un nouveau GO ; ne pas contourner le contrôle automatique.

Ne pas relancer de banc VM maintenant. Si un nouveau GO est donné ultérieurement, examiner `objects.json` et la configuration exacte avant toute action. Le contrôleur peut réutiliser UNIQUEMENT ses deux conteneurs labellisés, crée de nouvelles bases par tentative et arrête ces deux conteneurs en finally ; il ne supprime rien. Exemple de préflight en lecture seule côté VM (aucun mot de passe en argument/fichier) :

```bash
ssh pepeuch@192.168.10.191
sudo env PYTHONDONTWRITEBYTECODE=1 python3 /var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/code-v6/isolated_docker_bench.py --root /var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03
```

**Ne pas ajouter `--execute` sans nouveau GO.** Ancienne authentification SSH par clés refusée ; mot de passe explicitement fourni en conversation limité à VM150, non enregistré. Si connexion impossible, ne pas modifier l’authentification ou chercher d’autres credentials. Aucun autre accès Proxmox.

Points de reprise prioritaires après revue : statuer sur choix/licence DB ; définir le writer incrémental protégé (ordre de capture, état attendu, CAS/staging, partitions domaines/comptes) sans changer les identités ; vrais fournisseurs/fraîcheur/quotas uniquement avec scope autorisé ; laisser le scheduler, OS et 3.1 fermés tant que non autorisés.

## 7. État Git exact après création du checkpoint

- Branche : `feat/todo-phases-0-3`.
- HEAD : `d9180f6baefff1cbe500e3d263ec18c9f407382d`.
- Ref main : `d9180f6baefff1cbe500e3d263ec18c9f407382d` (inchangée).
- Index : vide, aucun fichier staged. Aucun commit/push/merge de la mission.
- 7 fichiers suivis modifiés, 124 nouveaux fichiers non suivis.
- Le statut complet ci-dessous et [CHECKPOINT_20261028_GIT_STATUS.txt](CHECKPOINT_20261028_GIT_STATUS.txt) incluent ce checkpoint et ses annexes. Aucun artefact supprimé.

```text
 M README.md
 M TODO.md
 M docs/architecture/overview.md
 M docs/quickstart/quickstart.md
 M infrastructure/proxmox/README.md
 M infrastructure/proxmox/create-ai-vm.sh
 M infrastructure/server/NVIDIA-README.md
?? database/poc/COMPARISON_PHASE2.md
?? database/poc/ISOLATED_DOCKER_BENCH.md
?? database/poc/MANUAL_INCREMENTAL_RUN.md
?? database/poc/comparison_workload.py
?? database/poc/confirmed_sql_batches.py
?? database/poc/fixtures/comparison.synthetic.json
?? database/poc/fixtures/surreal_explain_334.observed_sanitized.json
?? database/poc/incremental_import_plan.py
?? database/poc/isolated_bench_clients.py
?? database/poc/isolated_bench_ingestion.py
?? database/poc/isolated_bench_plans.py
?? database/poc/isolated_bench_runtime.py
?? database/poc/isolated_bench_workload.py
?? database/poc/isolated_docker_bench.py
?? database/poc/manual_discovery_run.py
?? database/poc/results/20261028-vm150-isolated-session/events.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/1000/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/1000/restore.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/stage.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/10000/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/10000/restore.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/stage.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/30/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/30/restore.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/stage.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated-session/final/discovery/baseline.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated-session/final/discovery/discovery_qualification.json
?? database/poc/results/20261028-vm150-isolated-session/final/discovery/partial.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated-session/final/discovery/revision.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated-session/final/discovery/same-name-pair.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated-session/final/preflight.json
?? database/poc/results/20261028-vm150-isolated-session/final/resource_samples.json
?? database/poc/results/20261028-vm150-isolated-session/final/result.json
?? database/poc/results/20261028-vm150-isolated-session/final/versions.json
?? database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T165927Z-4831d4/result.json
?? database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170130Z-eff462/result.json
?? database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170315Z-d846b7/result.json
?? database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170525Z-a923a3/result.json
?? database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T171940Z-0545fe/result.json
?? database/poc/results/20261028-vm150-isolated-session/review-manifest.json
?? database/poc/results/20261028-vm150-isolated/events.jsonl
?? database/poc/results/20261028-vm150-isolated/final/1000/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/1000/restore.json
?? database/poc/results/20261028-vm150-isolated/final/1000/stage.json
?? database/poc/results/20261028-vm150-isolated/final/1000/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/10000/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/10000/restore.json
?? database/poc/results/20261028-vm150-isolated/final/10000/stage.json
?? database/poc/results/20261028-vm150-isolated/final/10000/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/30/postgres-indexes.sql
?? database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/30/restore.json
?? database/poc/results/20261028-vm150-isolated/final/30/stage.json
?? database/poc/results/20261028-vm150-isolated/final/30/surreal-indexes.surql
?? database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-ingestion.json
?? database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-plan.json
?? database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-receipts.jsonl
?? database/poc/results/20261028-vm150-isolated/final/discovery/baseline.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated/final/discovery/discovery_qualification.json
?? database/poc/results/20261028-vm150-isolated/final/discovery/partial.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated/final/discovery/revision.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated/final/discovery/same-name-pair.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-isolated/final/preflight.json
?? database/poc/results/20261028-vm150-isolated/final/resource_samples.json
?? database/poc/results/20261028-vm150-isolated/final/result.json
?? database/poc/results/20261028-vm150-isolated/final/versions.json
?? database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T165927Z-4831d4/result.json
?? database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170130Z-eff462/result.json
?? database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170315Z-d846b7/result.json
?? database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170525Z-a923a3/result.json
?? database/poc/results/20261028-vm150-isolated/review-manifest.json
?? database/poc/test_comparison_workload.py
?? database/poc/test_incremental_import_plan.py
?? database/poc/test_isolated_bench.py
?? database/poc/test_isolated_bench_contracts.py
?? database/poc/test_isolated_bench_results.py
?? database/poc/test_manual_discovery_run.py
?? docs/audit/CHECKPOINT_20261028_GIT_STATUS.txt
?? docs/audit/CHECKPOINT_20261028_PHASES_0_3.md
?? docs/audit/PHASES_0_3_COVERAGE.md
?? docs/audit/README_ABOUT_PLAN.md
?? docs/audit/TODO_PHASES_0_3_20261028.snapshot.txt
?? docs/infrastructure/STORAGE_AND_VALIDATION.md
?? docs/infrastructure/VM150_GPU_20261028.md
?? docs/infrastructure/VM150_READONLY_20261028.md
?? infrastructure/proxmox/vm_plan.py
?? infrastructure/server/inspect_poc_health.py
?? tests/infrastructure/test_poc_health.py
?? tests/infrastructure/test_vm_plan.py
```
