# Checkpoint durable de reprise — phases 0 à 3 — 2026-10-28T21:51:06+01:00

## Situation et périmètre

Reprise expressément autorisée depuis [le checkpoint précédent](CHECKPOINT_20261028_PHASES_0_3.md).
Branche `feat/todo-phases-0-3`, HEAD `d9180f6baefff1cbe500e3d263ec18c9f407382d`, ref `main` identique et inchangée.
Aucun commit, staging, push, merge, suppression, nettoyage global ou écrasement
unrelated. Aucun accès Proxmox, HAOS, NAS, GPU, modèle ou inférence.
Le dépôt `/opt/pepeuch-ai/repo` sur VM150 n’a pas été synchronisé.
Arrêt strict **avant `## 3.1 models.dev`** ; suffixe identique à HEAD.

TODO exacte jusqu’à cette borne : [snapshot de reprise](TODO_PHASES_0_3_20261028_REPRISE.snapshot.txt).
SHA256 préfixe : `15b2e8d2e95f47da71d73343828232213411b0ff9eb602b9edc81202bfda0e9d`.
SHA256 suffixe 3.1+ : `52cb52ee4afce412e6306f60e0fe38752dd4c52dc67fa115dd5ce872b283fe34`.
49 cases initialement ouvertes ; 14 clôturées précédemment, **35 composites toujours ouvertes**
(phase 1 : 29 ; phase 2 : 4 ; phase 3 générale : 2). Une **nouvelle sous-tâche**
anti-rejeu est cochée sur preuves réelles ; elle ne clôture pas l’industrialisation.
Les snapshots du checkpoint précédent restent conservés et ne décrivent pas la nouvelle TODO.

## Travaux de cette reprise

**IMPLEMENTED / TESTED / VERIFIED sur synthétique** : `emit_discovery_import.py`
produit désormais du SQL qui contrôle l’état stocké dans la transaction d’écriture.
Un ancien `captured_at`, même à payload identique, ou un autre contenu/snapshot
au même instant fait échouer toute la transaction. Rejeu exact et dates à fuseaux
différents représentant le même instant acceptés. Aucune suppression/non-observation
transformée en suppression. Identités, provenance du payload, inconnues et relations préservées.

PostgreSQL : COPY temporaire, READ COMMITTED, verrou SHARE ROW EXCLUSIVE avant
contrôle/upsert. SurrealDB : OPTION IMPORT, transaction, DEFINE TABLE IF NOT EXISTS,
contrôles/upserts/commit ; corps complet borné à 524288 octets UTF-8, refus sans
sortie partielle au-delà. Aucun repli vers l’ancienne génération non protégée.
La CLI et les signatures restent disponibles, mais les sorties SQL changent
volontairement ; le format et les empreintes B2/B3 ne changent pas.

Le contrôleur existant ajoute `--qualification-only`, indépendant des performances.
Le runtime distingue le rejeu protégé des probes volontairement non protégés.
Huit tests de non-régression nouveaux : structure/ordre transactionnel, dates,
UTF-8 et refus de préfixe, conservation/inconnues, intégrité des artefacts et
qualification réelle. [Contrat complet](../../database/poc/REPLAY_GUARD_PHASE3.md).

**Limites non masquées** : les vieux SQL/bundles restent sans garde rétroactive.
La date déclarée n’est pas une preuve de révision fournisseur ni d’origine ; un
payload réhorodaté peut passer. Protection par ressource, pas un ordre global de
scope. Pas de CAS complet, stockage cloisonné domaine/compte, plan exécutable,
service automatisé ou scheduler. Concurrence entre transactions non exercée
réellement dans ce lot ; mécanismes SQL présents, preuve de concurrence à ajouter.
Les champs `legacy_generators_guarded=false` du plan/probe CAS concernent le
protocole CAS complet, pas la nouvelle garde temporelle.

## Qualification réelle VM150 et artefacts

Accès existant à `pepeuch@192.168.10.191`, sudo limité aux opérations du banc.
Aucun credential enregistré dans les documents, scripts ou exports. Clés SSH
précédemment refusées ; ne pas modifier l’authentification ni chercher d’autres
credentials. Le mot de passe fourni par l’utilisateur reste uniquement en conversation.
Aucun accès supplémentaire Proxmox autorisé.

Racine VM : `/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03`.
Deux conteneurs temporaires existants, images exactes locales, 2 CPU / 4 Gio /
256 PID, sans privilèges, réseau interne sans port publié ; IDs vérifiés avant essai :
- PG `ea3bba2b497fd5160ebada8a3bc751f6a8a0ac999231d2f7a99ccebd0f4c566a`.
- Surreal `b740e2d06ed8fdeba1be53eebd577b72f8235d2fdb430a2cbca838cf060c258c`.
**Les deux sont arrêtés en fin d’essai.** Images : PG
`sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab`,
Surreal `sha256:649a60a3b9c0177d9923c938e1c2563e48cde2a9d06ac2c0519714be719b02af`.

| Essai | Résultat | Preuve / anomalie |
|---|---|---|
| `attempt-20261028T204033Z-e34907` | FAILED | Surreal HTTP 422 au premier import ; arrêt des deux conteneurs |
| `attempt-20261028T204222Z-f7c9c5` | FAILED conservé | Diagnostic JSON : SELECT d’une table absente → NotFound/Table ; transaction annulée |
| `attempt-20261028T204333Z-a15681` | VERIFIED | Définition conditionnelle dans transaction ; anciens rejeux/conflits refusés, équivalence fuseaux et deux restaurations réussies |

Série finale **21:43:33–21:43:36 Europe/Paris**, PostgreSQL 16.15 / SurrealDB 3.3.4.
Trois refus attendus par moteur : ancienne révision, ancienne date à payload
identique, même instant conflictuel avec nouvelle ligne. PG exit 3 / Surreal HTTP422
et état intégral inchangé après chaque cas. Neuf ressources finales restaurées
vers `discovery_4e5c3ea1_restore` dans chaque moteur, destinations distinctes.
Pas de collecte fournisseur ni SQL sur POC historiques. Les fingerprints de leurs
IDs/images/états/dates/montages sont égaux avant/après les trois essais ; cela ne
constitue pas une revalidation de leurs données historiques, toujours arrêtées.

Le watchdog et les seuils du banc sont conservés. **Un seul prélèvement** pour
le dernier essai court : ce n’est pas une nouvelle mesure de pic CPU/RAM sur toute
la qualification. Aucun mélange avec le benchmark v6, aucun nouveau p50/p95.

Conservés sur VM : tous les anciens dossiers/données et nouveaux `code-guard-*`,
`bundle-guard-*`, trois nouveaux `attempt-*`, dumps/exports et diagnostics. Source
finale `code-guard-784f0d068754/database/poc`, bundle SHA256
`bba7cb7bafadb8ae1880ec14f495a20a396232793eb6171396812faae4861126`.
La seule différence ultérieure du module de plan est documentaire ; les deux tests
supplémentaires de preuves ont été ajoutés après export (VM bundle : 345 tests,
suite locale actuelle : 347). Les fichiers exécutant la garde correspondent au bundle final.
Archive VM `review-replay-guard-784f0d068754.tgz`, SHA256
`8998708b4c6f12ab36b41fbfd38510b0cec646d636743752dc853b5610e1c9ce`.
Copie locale durable : `database/poc/results/20261028-vm150-replay-guard/`, **25 fichiers**
(manifeste + 24 preuves), SHA/tailles vérifiés. Les dumps restent sur VM ; le rapport
conserve leurs empreintes. Les fichiers privés `surreal.private.env` ne sont pas exportés.
Aucun artefact, volume ou ancienne tentative supprimé.

## Benchmarks précédents conservés, sans nouveau chronométrage

Série autoritative inchangée : `attempt-20261028T173131Z-7490ca`, code-v6,
`database/poc/results/20261028-vm150-isolated-session/` (46 fichiers).
Profil Basic v5 provisoire conservé séparément dans `.../20261028-vm150-isolated/`
(45 fichiers), sans mélange. Tous les SHA/tailles référencés par les deux manifestes
ont été revérifiés ; les mesures et plans restent les originaux.

À 10000 modèles, après index additionnels, p50/p95 normaux en ms :

| Requête | PostgreSQL | SurrealDB |
|---|---:|---:|
| provider_filter | 0.398 / 2.944 | 4.331 / 7.205 |
| base_quant | 0.496 / 0.644 | 87.272 / 90.139 |
| provider_cost | 0.276 / 0.394 | 4.917 / 5.088 |
| runtime_gpu | 0.826 / 2.837 | 132.968 / 147.536 |
| role_candidate | 0.558 / 0.786 | 51.667 / 54.699 |
| local_benchmark | 0.174 / 0.307 | 10.335 / 11.512 |
| vector_exact | 17.174 / 19.377 | 20.688 / 24.877 |
| hybrid_exact | 19.283 / 20.031 | 24.347 / 27.008 |

Pic mémoire cgroup : PG 157.01 Mio / Surreal 625.25 Mio ; CPU delta échantillonné
5.064 s / 24.334 s ; PIDmax 9 / 30. Disque apparent cumulé 369.98 / 169.06 Mio,
incluant les essais antérieurs, donc pas une comparaison de stockage par dataset.
Index : profils baseline et additionnels conservés en SQL/SurrealQL dans chaque
palier 30/1000/10000. Requêtes et plans obligatoires ; latence normale et métriques
EXPLAIN séparées. 15 échantillons/cas ; p95 nearest-rank = maximum ici, pas une
estimation de production robuste. Vecteurs exacts synthétiques 16D, pas ANN/BM25,
concurrence/coldcache/qualité sémantique non vérifiées. PostgreSQL reste un candidat
conditionnel pour cette charge ; aucune adoption ou licence d’usage approuvée.
Rapport complet : [banc initial](../../database/poc/ISOLATED_DOCKER_BENCH.md).

## État exact des 35 cases encore ouvertes

Aucune case composite cochée sans ses preuves. Les lignes sont celles de la
TODO de reprise annexée ; certains blocages sont des décisions ou validations
futures, pas des défauts à corriger en code local.

| Ligne TODO | Case ouverte | État | Preuve actuelle / manque |
|---:|---|---|---|
| 115 | Créer la VM via le script Proxmox | BLOCKED | G1 : VM jetable et autorisation Proxmox absentes ; plan logiciel testé seulement. |
| 126 | Définir sauvegarde de la VM | BLOCKED | G1 : politique préparée ; sauvegarde réelle Proxmox non autorisée. |
| 138 | Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables. | BLOCKED | G1 : restauration vers VMID distinct non autorisée, aucun accès Proxmox. |
| 139 | Confirmer la disponibilité courante des healthchecks des deux bases après autorisation : cinq dernières sondes de chaque base réussies avant l’arrêt, mais conteneurs actuellement arrêtés ; aucun démarrage autorisé. | BLOCKED | POC historiques arrêtés, aucun GO de démarrage ; cinq sondes historiques réussies seulement. |
| 182 | Étendre les sondes à plusieurs modèles et formats ; vérifier les révisions, fichiers, relations et éventuelles restrictions d'accès. L'API sondée ne fournit pas de SHA Git exploitable. | BLOCKED | Extension spécifique de source / révisions distantes : différée avant 3.1 ; pas de sonde supplémentaire. |
| 192 | Étendre les sondes à d'autres dépôts et étudier séparément les ressources datasets, spaces, MCP, skills et les modèles servis par l'AI Gateway. | BLOCKED | Autres dépôts et familles de ressources : différés ; pas de collecte réelle. |
| 202 | Synchroniser les fichiers locaux non suivis de la VM avec la branche publiée, après comparaison ; voir [la procédure ciblée](database/poc/MOARK_VM_SYNC.md). | BLOCKED | Dépôt VM encore au checkpoint B5.2 ; pas de synchronisation autorisée ni comparaison complète des locaux. |
| 203 | Étudier séparément capacités, quotas applicables et dépôts de poids MoArk/Gitee ; aucune association automatique par nom. | BLOCKED | Étude propre à MoArk/Gitee différée, aucune preuve d’inférence ou de poids. |
| 215 | Décider la sémantique future des accès/visibilités, de l'isolation domaines/comptes, des révisions et des collectes partielles avant toute évolution de format ou d'identité. | PARTIAL | B2 conservé et garde temporelle qualifiée ; accès, namespaces et ordre de révision fournisseur à décider. |
| 231 | Décider et tester la politique de redirections B1 avant sa migration ; préserver le cas NIM 404 et les limites du SDK. Voir [TRANSPORT_B42.md](database/poc/TRANSPORT_B42.md). | PARTIAL | Transport commun deny-redirect testé ; politique/migration B1 historique et garanties SDK encore ouvertes. |
| 239 | Examiner le prototype et décider multitag NIM, namespaces domaines/comptes, provenance synthétique/réelle et conventions de collecte partielle avant un registre opérationnel. | PARTIAL | Registre sur fixtures opérationnel ; multitag NIM, domaines/comptes et partiels attendent décision. |
| 248 | Examiner le registre manuel avant toute extension online ; provenance synthétique/réelle, domaines/comptes, NIM multitag et résultats partiels restent à décider. | PARTIAL | Sept sources sur fixtures ; mêmes décisions sémantiques requises avant online. |
| 258 | Décider la provenance obligatoire et le contrat d'import avant toute protection complète du B2 brut ; l'option ne remplace pas une validation d'origine. | PARTIAL | SQL régénéré garde les dates, provenance protégée opt-in ; origine obligatoire du B2 brut/CAS/cloisonnement non finalisés. |
| 268 | Définir l'enrôlement/rotation/révocation des émetteurs et la CLI protégée ; HMAC local ne prouve pas une collecte distante. | PARTIAL | Attestation locale HMAC testée ; émetteurs, rotation/révocation et CLI contrôlée non raccordés. |
| 269 | Raccorder les reçus HTTP conditionnels au moteur budgété, la reprise inter-sources et les politiques de fraîcheur avant de déclarer B4.5 opérationnel. | PARTIAL | Archives/fraîcheur/reprise locale testées ; HTTP 304 non raccordé au moteur budgété. |
| 270 | Définir pagination distante, garanties/quotas SDK, concurrence par hôte et budget global dans des lots séparés ; aucun scheduler. | PARTIAL | Budgets coopératifs par source ; pagination/SDK, plafond global et concurrence restent distincts, aucun scheduler. |
| 279 | Valider les contrats d'identité/appairage/bail et l'API de mission avant B5.1 ; développer un faux worker puis autoriser séparément un pilote Linux CPU. | PARTIAL | Contrats locaux/faux worker CPU testés ; appairage/TLS et pilote OS non qualifiés. |
| 280 | Choisir langage/packaging, stockage durable et politique de clés ; vérifier licences/artefacts exacts, notamment Desktop avant toute redistribution. | PARTIAL | Python/SQLite prototype ; packaging, politique de clés et licences de redistribution exactes non décidés. |
| 281 | Établir une matrice réellement testée par OS/runtime ; aucune capacité GPU/inférence/agent annoncée comme vérifiée par cette étude. | BLOCKED | Matrice multi-OS/runtime exige des machines et essais dédiés ; Linux applicatif ne suffit pas. |
| 282 | Garder interfaces tierces, VM automatisée, compagnon multi-OS et USB dans des lots séparés ; aucune installation/provisionnement/migration effectués dans B5.0. | PARTIAL | Séparation VM/compagnon/USB/interfaces documentée, livraisons futures non effectuées. |
| 294 | Finaliser la pile HTTP de production et l'isolation OS d'un vrai worker ; les contrôles locaux HTTP/identité/sauvegarde sont validés au checkpoint B5.2, sans exposition LAN. | PARTIAL / BLOCKED | 123 tests Control Plane passés ; pile production/isolation OS non qualifiées. |
| 295 | Définir les contrats agents/rôles/baux réels, appairage/TLS et politiques multi-utilisateurs avant une ouverture LAN ou exécution d'outils ; aucune installation, inférence ou collecte réelle dans B5.1. | BLOCKED | Contrats agents/outils/TLS multi-utilisateurs réels hors prototype, aucune ouverture LAN. |
| 307 | Avant un vrai worker : isolation OS éprouvée, politiques réseau/outils/enfants, PKI/appairage/TLS et pile HTTP de production ; conserver le prototype sans IA réelle ni découverte LAN. | PARTIAL / BLOCKED | 48 tests worker et 63 isolation applicative passés ; pilotes OS/PKI/production non qualifiés. |
| 317 | Autoriser puis exécuter les tests négatifs OS sur une machine distincte : UID/groupes, secrets/SQLite/objets inaccessibles, FS, réseau, GPU/Docker, CPU/RAM/PID, runtime et arrêt des enfants — **NOT VERIFIED**. | BLOCKED | G3 : aucune VM jetable/permission de comptes, unités ou pare-feu ; pas de tests négatifs OS. |
| 318 | Qualifier le producteur indépendant de permis et fermer/vérifier le réseau OS au port backend ; contrats, observations et canal de refus ajoutés en B5.3.1, sans activation. `--application-test` ne valide pas l'isolation, le filtre IP candidat seul autorise tous les ports loopback. | PARTIAL / BLOCKED | Canal de refus et guards applicatifs testés ; preuve indépendante et filtrage OS des ports non qualifiés. |
| 319 | Avant une inférence ou un outil réel : contrat de lecture des versions d'entrée, quotas cumulés I/O/calcul, politique des moteurs/outils, preuves OS et profils Windows/macOS distincts ; conserver AnythingLLM/Open WebUI facultatifs. | BLOCKED | Entrées/outils/runtimes et quotas cumulés, profils Windows/macOS et preuves OS restent à concevoir/valider. |
| 329 | Autoriser un pilote négatif sur une **VM jetable distincte** selon [le plan opérateur Debian](docs/architecture/B53_DEBIAN13_VALIDATION.md), avec confirmations séparées pour comptes, fichiers, unités et pare-feu. Aucun accès à la VM historique autorisé. | BLOCKED | G3 : pilote Debian négatif exige une VM distincte explicitement autorisée. |
| 330 | Qualifier collecte indépendante, compte exclusif, code/FD/montages, règles/IPv4/IPv6/ports et ressources/arrêt avant un producteur de permis positif. Le contrôleur livré émet toujours `deny` ; strict reste bloqué, OS **NOT VERIFIED**. | PARTIAL / BLOCKED | Contrôleur deny conservé ; compte, code/FD, IPv4/IPv6/ports et ressources non qualifiés réellement. |
| 331 | Définir si nécessaire une attestation serveur distincte : aucun champ worker ne promeut aujourd'hui le statut `verified`. Pas de vraie inférence, modèle, GPU ou service privilégié permanent. | BLOCKED | Décision d’attestation serveur distincte requise ; aucune promotion verified par un worker. |
| 353 | Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation). | PARTIAL | Banc représentatif terminé sur synthétique, limites connues ; clôture globale conditionnée à revue exploitation/licence. |
| 365 | Vérifier précisément les contraintes de licence de SurrealDB avant adoption | PARTIAL / BLOCKED | Texte exact BSL du tag étudié ; usage/distribution et notices de l’image à valider avant adoption. |
| 366 | Décider du moteur principal | BLOCKED | Recommandation PostgreSQL conditionnelle documentée ; choix de projet à confirmer. |
| 367 | Documenter la décision | BLOCKED | Rapport disponible ; ADR finale attend la décision, aucune adoption implicite. |
| 432 | Industrialiser l'ingestion incrémentale (exécution planifiée, reprise sur erreur, rétention, surveillance) ; le POC B2 est une importation **manuelle**, pas encore un Discovery Service en production. | PARTIAL | Garde anti-rejeu réelle ajoutée ; CAS général, provenance/partitions, scheduler/rétention/surveillance non livrés. |
| 441 | Éprouver les imports partiellement échoués, les changements de révision réels et les variations de périmètre ; conserver les snapshots et définir la politique de rafraîchissement. | PARTIAL | Échecs/reprises/restaurations synthétiques et scopes validés ; révisions distantes et rafraîchissement opérationnel manquants. |

## Tests et vérifications de cette session

| Suite locale | Résultat actuel |
|---|---:|
| Discovery `database/poc` | 347 OK, dont 8 nouveaux |
| Control Plane | 123 OK |
| Worker | 48 OK |
| Isolation applicative | 63 OK ; pas une preuve OS négative |
| Infrastructure simulée | 19 OK |
| Total de la vague locale | **600 tests réussis** |

Première tentative CP dans le sandbox : 43 erreurs de sockets refusées, puis
relance autorisée sous l’UID courant hors sandbox : 123/123 réussis. Aucun code
Control Plane/worker/isolation modifié. Sur VM : 345 tests ont passé avant le premier
essai ; les deux essais suivants utilisent de nouveaux bundles, la qualification
finale réussit avec la correction DEFINE. Ne pas présenter cela comme une relance
complète des 347 tests locaux sur le code final de la VM.

Référence B3.3 SHA256 inchangée :
`ef2e2834d86448aa5ef5ee8b95f5b6d42555684b0a588b837d83abb0775d36bd`.
Les suites historiques passent sans modifier leurs attendus. Les empreintes des
anciens artefacts sont contrôlées par les tests. `git diff --check` est à nouveau
exécuté après ce checkpoint ; le suffixe TODO 3.1+ est identique à HEAD.
Aucun nouveau secret dans les fixtures/logs/documents ; les réponses exportées
sont synthétiques, sans headers ni credentials.

## Reprise : lots prioritaires et commandes

1. Relire ce checkpoint, la TODO/matrice et REPLAY_GUARD_PHASE3 ; préserver l’arbre.
2. Revoir le choix DB et l’usage/licence, sans déclarer une adoption implicitement.
3. Lot logiciel général suivant : CAS attendu-state et contrat de publication
   (ordre de capture/fournisseur, provenance obligatoire, partitions), puis tests
   de concurrence sur destinations synthétiques explicitement isolées.
4. Lot séparé : raccordement HTTP304/budgets/reprise/fraîcheur, puis gestion locale
   des émetteurs/CLI ; aucun scheduler ni collecte fournisseur implicite.
5. G1 Proxmox/backup et G3 OS restent bloqués sans autorisation spécifique et VM
   jetable distincte. Ne pas démarrer les POC historiques. Ne pas commencer 3.1.

Commandes locales sans base ni fournisseur :

```bash
git status --short --untracked-files=all
git branch --show-current
git rev-parse HEAD
git diff --check
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s database/poc -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/control_plane -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/worker -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/isolation -p 'test_*.py' -q
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/infrastructure -p 'test_*.py' -q
```

Les quatre dernières suites peuvent nécessiter l’exécution hors sandbox sous
l’UID courant pour loopback/SO_PASSCRED/permissions simulées ; pas root local.
Pour revoir le banc VM, lecture seule d’abord, jamais d’authentification en
argument ou document. Ne pas relancer le benchmark de performance pour tester
uniquement le garde. Exemple de préflight, **sans --execute** :

```bash
ssh pepeuch@192.168.10.191
sudo env PYTHONDONTWRITEBYTECODE=1 python3 /var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/code-guard-784f0d068754/database/poc/isolated_docker_bench.py --root /var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03 --qualification-only
```

Toute nouvelle exécution doit conserver les deux IDs temporaires contrôlés,
les nouveaux noms de bases, limites/monitor et arrêt en finally ; aucun prune/rm,
aucun fichier d’artefact écrasé. Le dépôt VM150 reste indépendant et ancien.

## État Git exact après création des annexes

Branche `feat/todo-phases-0-3`, HEAD `d9180f6baefff1cbe500e3d263ec18c9f407382d` ; index vide.
**9 fichiers suivis modifiés et 154 fichiers non suivis** ; aucune
suppression/staging/commit/push/merge. `main` préservée. Par rapport au checkpoint
précédent : générateur SQL et sa documentation B2 modifiés ; runtime/contrôleur,
plan (documentation), manuel incrémental et matrice mis à jour ; nouveau test,
rapport anti-rejeu, 25 preuves JSON et trois annexes de reprise. Les sept fichiers
suivis déjà modifiés avant cette reprise sont conservés.

Statut exhaustif : [CHECKPOINT_20261028_REPRISE_GIT_STATUS.txt](CHECKPOINT_20261028_REPRISE_GIT_STATUS.txt).

```text
 M README.md
 M TODO.md
 M database/poc/DISCOVERY_CACHE_B2.md
 M database/poc/emit_discovery_import.py
 M docs/architecture/overview.md
 M docs/quickstart/quickstart.md
 M infrastructure/proxmox/README.md
 M infrastructure/proxmox/create-ai-vm.sh
 M infrastructure/server/NVIDIA-README.md
?? database/poc/COMPARISON_PHASE2.md
?? database/poc/ISOLATED_DOCKER_BENCH.md
?? database/poc/MANUAL_INCREMENTAL_RUN.md
?? database/poc/REPLAY_GUARD_PHASE3.md
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
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/baseline.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/partial.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/revision.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/preflight.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/resource_samples.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/result.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/versions.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/baseline.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/partial.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/revision.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/surreal-import-error-31806168.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/preflight.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/resource_samples.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/result.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/versions.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/baseline.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/discovery_qualification.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/partial.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/revision.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/same-name-pair.snapshot.synthetic.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/preflight.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/resource_samples.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/result.json
?? database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/versions.json
?? database/poc/results/20261028-vm150-replay-guard/review-manifest.json
?? database/poc/test_comparison_workload.py
?? database/poc/test_discovery_replay_guard.py
?? database/poc/test_incremental_import_plan.py
?? database/poc/test_isolated_bench.py
?? database/poc/test_isolated_bench_contracts.py
?? database/poc/test_isolated_bench_results.py
?? database/poc/test_manual_discovery_run.py
?? docs/audit/CHECKPOINT_20261028_GIT_STATUS.txt
?? docs/audit/CHECKPOINT_20261028_PHASES_0_3.md
?? docs/audit/CHECKPOINT_20261028_REPRISE_GIT_STATUS.txt
?? docs/audit/CHECKPOINT_20261028_REPRISE_PHASES_0_3.md
?? docs/audit/PHASES_0_3_COVERAGE.md
?? docs/audit/README_ABOUT_PLAN.md
?? docs/audit/TODO_PHASES_0_3_20261028.snapshot.txt
?? docs/audit/TODO_PHASES_0_3_20261028_REPRISE.snapshot.txt
?? docs/infrastructure/STORAGE_AND_VALIDATION.md
?? docs/infrastructure/VM150_GPU_20261028.md
?? docs/infrastructure/VM150_READONLY_20261028.md
?? infrastructure/proxmox/vm_plan.py
?? infrastructure/server/inspect_poc_health.py
?? tests/infrastructure/test_poc_health.py
?? tests/infrastructure/test_vm_plan.py
```
