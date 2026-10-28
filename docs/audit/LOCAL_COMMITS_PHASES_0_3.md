# Préparation des commits locaux — phases 0 à 3

Date : 2026-10-28T22:26:40+01:00.
Autorisation explicite de commits **locaux seulement** ; aucun push, merge,
rebase, modification de main ou intervention système/VM.

## État vérifié avant préparation

Branche `feat/todo-phases-0-3`, HEAD et main
`d9180f6baefff1cbe500e3d263ec18c9f407382d`, index vide.
Inventaire initial : **9 fichiers suivis modifiés + 154 non suivis = 163**,
2 730 716 octets. Aucun lien symbolique ou binaire parmi eux. Aucun fichier
ne dépasse 270 000 octets ; les plus gros sont six `stage.json` de campagnes.
Les fichiers temporaires `/tmp` et les données/bundles/dumps de VM150 sont hors
périmètre d’ajout. Aucun dump DB, volume, clé ou fichier d’authentification importé.

## Classification et exclusions

**116 fichiers / 2 166 835 octets** d’exports opérationnels sont privés et exclus
intégralement, sans sélection opportuniste ni modification de leur contenu :

| Répertoire local ignoré par Git | Fichiers | Nature |
|---|---:|---|
| `database/poc/results/20261028-vm150-isolated/` | 45 | Série Basic provisoire, erreurs et preuves |
| `database/poc/results/20261028-vm150-isolated-session/` | 46 | Série finale v6, plans/mesures/reçus et métadonnées VM |
| `database/poc/results/20261028-vm150-replay-guard/` | 25 | Qualifications anti-rejeu, diagnostics et métadonnées VM |

Leurs 116 empreintes ont été comparées à l’inventaire avant préparation :
**aucun résultat modifié**. Les manifestes restent disponibles localement.
Les règles `.gitignore` ciblent ces trois répertoires, pas les fixtures.

Sur VM150, les artefacts restent sous
`/var/tmp/pepeuch-dbbench-20261028t165804z-a8e6ef03/` : données, volumes, dumps,
exports, anciens essais et `surreal.private.env` privé. Aucun accès VM, conteneur
ou Proxmox durant cette préparation ; aucun de ces fichiers n’est ajouté.
Les copies d’archives de travail sous `/tmp/pepeuch-*` et `/tmp/review-*` restent
hors Git, sans suppression. Les sauvegardes locales de préparation sont aussi
sous `/tmp/phases-*` ; elles ne sont pas ajoutées.

**Versionnés** : code, tests, fixtures synthétiques, réponse EXPLAIN déjà masquée,
rapports de synthèse, TODO, procédures et checkpoints historiques. Ces documents
conservent les versions et identifiants techniques nécessaires à l’audit, parfois
les adresses LAN/chemins fournis par l’utilisateur ; aucun credential ni contenu
de base privée. Les checkpoints sont des photographies datées, non réécrites pour
simuler un état Git après commit. Leurs anciennes affirmations « aucun commit »
et listes de fichiers non suivis décrivent leur date, pas l’état après ce lot.
Les liens vers `results/` sont des références d’artefacts privés absents d’un clone.

## Organisation des tests et compatibilité

[Commandes et inventaire détaillé](../../tests/README.md). Sept modules nouveaux
(75 cas) rejoignent `tests/discovery/`. Les vingt modules historiques (272 cas)
restent en place pour les chemins de fixtures/CLI et imports de helpers.
Deux relais maintiennent la découverte complète historique et le point d’entrée
centralisé : **mêmes 347 identifiants uniques**, sans duplication ni récursion.

Aucune assertion ni référence n’est modifiée par le déplacement ; comparaison
AST des sept corps de tests et empreintes de toutes les fixtures conservées.
Les trois chemins de ressources déplacés sont ancrés sur le dossier POC original.
Les benchmarks exécutables restent séparés et ne sont pas lancés ici.

Pour distribuer le code sans données privées, sept contrôles d’intégrité de
preuves locales signalent explicitement `skipped` quand leur dossier est absent.
Cette précondition de confidentialité est séparée de la réorganisation ; toutes
leurs assertions s’exécutent si les données sont présentes, une présence partielle
ou corrompue échoue. Aucun téléchargement/faux résultat ne remplace les exports.

Validation avec exports privés présents : `python3 tests/run_suites.py -q`,
**600 succès** : Discovery 347, Control Plane 123, infrastructure 19, isolation
applicative 63, worker 48. Les deux commandes Discovery (historique et centralisée)
passent aussi chacune à 347 ; aucun nouveau benchmark ou test GPU/OS privilégié.
Une copie portable sans données privées vérifie séparément 340 succès Discovery
et sept `skipped` ; les 253 autres cas restent indépendants de ces exports.
Les 600 succès ne sont donc pas annoncés comme entièrement reproductibles sans
les sept preuves privées. Les anciennes validations VM restent rapportées, pas
réexécutées par la préparation.

## Lots sélectionnés et dépendances

| Ordre | Message | Fichiers |
|---:|---|---:|
| 1 | `fix(infra): harden VM planning and document VM150 validation` | 10 |
| 2 | `test: centralize discovery entry points and exclude private campaigns` | 7 |
| 3 | `feat(discovery): add manual checkpoint execution and incremental import plans` | 5 |
| 4 | `fix(discovery): reject stale and conflicting B2 snapshot imports` | 4 |
| 5 | `feat(poc): add isolated database benchmark and confirmed batch qualification` | 16 |
| 6 | `docs: record phases 0-3 evidence, TODO status and local commit inventory` | 14 |

**56 chemins distincts** versionnés (46 nouveaux et 10 fichiers déjà suivis).
Le socle infrastructure précède le lanceur global ; l’organisation des tests
précède leurs nouvelles suites ; la garde B2 précède le runtime qui la qualifie.
Les liens documentaires sont complets au dernier lot. L’ajout est explicite,
fichier par fichier depuis une liste qualifiée, sans `git add .`/`git add -A`.

Avant chaque commit : `git diff --check`, `git diff --cached --stat`,
`git diff --cached --check`, comparaison exacte index/liste autorisée, contrôle
secrets sur les blobs indexés et refus de tout chemin sous `database/poc/results/`.
Revue des secrets : clés privées, formats de tokens usuels, JWT, valeurs Basic/
Bearer et affectations sensibles. Le seul motif générique initial est le code
qui **génère** un mot de passe éphémère (`secrets.token_urlsafe`) et écrit le
fichier privé du banc ; aucune valeur réelle n’est incorporée. Les valeurs
synthétiques et masques sont distingués des credentials. Les références B3.3
et le suffixe TODO depuis 3.1 restent inchangés. Les deux snapshots verbatim
de TODO conservent leurs lignes blanches finales et leurs empreintes ; une règle
`.gitattributes` ciblée uniquement sur ces deux chemins désactive leur seul
contrôle `blank-at-eof`. Aucun autre contrôle d’espacement n’est désactivé.

Les SHA définitifs sont fournis après création ; la dernière empreinte ne peut
pas être incluse dans son propre contenu. Revue reproductible locale :

```bash
git log --reverse --oneline d9180f6baefff1cbe500e3d263ec18c9f407382d..HEAD
git diff --stat d9180f6baefff1cbe500e3d263ec18c9f407382d..HEAD
git status -sb
git status --short --ignored database/poc/results
git ls-files database/poc/results
```

## Inventaire des fichiers destinés aux commits

- Lot 1 : `infrastructure/proxmox/README.md`
- Lot 1 : `infrastructure/proxmox/create-ai-vm.sh`
- Lot 1 : `infrastructure/proxmox/vm_plan.py`
- Lot 1 : `infrastructure/server/NVIDIA-README.md`
- Lot 1 : `infrastructure/server/inspect_poc_health.py`
- Lot 1 : `tests/infrastructure/test_poc_health.py`
- Lot 1 : `tests/infrastructure/test_vm_plan.py`
- Lot 1 : `docs/infrastructure/STORAGE_AND_VALIDATION.md`
- Lot 1 : `docs/infrastructure/VM150_GPU_20261028.md`
- Lot 1 : `docs/infrastructure/VM150_READONLY_20261028.md`
- Lot 2 : `.gitignore`
- Lot 2 : `tests/__init__.py`
- Lot 2 : `tests/discovery/__init__.py`
- Lot 2 : `tests/run_suites.py`
- Lot 2 : `tests/README.md`
- Lot 2 : `database/poc/test_discovery_consolidation.py`
- Lot 2 : `database/poc/README.md`
- Lot 3 : `database/poc/manual_discovery_run.py`
- Lot 3 : `database/poc/incremental_import_plan.py`
- Lot 3 : `tests/discovery/test_manual_discovery_run.py`
- Lot 3 : `tests/discovery/test_incremental_import_plan.py`
- Lot 3 : `database/poc/MANUAL_INCREMENTAL_RUN.md`
- Lot 4 : `database/poc/emit_discovery_import.py`
- Lot 4 : `database/poc/DISCOVERY_CACHE_B2.md`
- Lot 4 : `database/poc/REPLAY_GUARD_PHASE3.md`
- Lot 4 : `tests/discovery/test_discovery_replay_guard.py`
- Lot 5 : `database/poc/comparison_workload.py`
- Lot 5 : `database/poc/confirmed_sql_batches.py`
- Lot 5 : `database/poc/isolated_bench_clients.py`
- Lot 5 : `database/poc/isolated_bench_ingestion.py`
- Lot 5 : `database/poc/isolated_bench_plans.py`
- Lot 5 : `database/poc/isolated_bench_runtime.py`
- Lot 5 : `database/poc/isolated_bench_workload.py`
- Lot 5 : `database/poc/isolated_docker_bench.py`
- Lot 5 : `tests/discovery/test_comparison_workload.py`
- Lot 5 : `tests/discovery/test_isolated_bench.py`
- Lot 5 : `tests/discovery/test_isolated_bench_contracts.py`
- Lot 5 : `tests/discovery/test_isolated_bench_results.py`
- Lot 5 : `database/poc/fixtures/comparison.synthetic.json`
- Lot 5 : `database/poc/fixtures/surreal_explain_334.observed_sanitized.json`
- Lot 5 : `database/poc/COMPARISON_PHASE2.md`
- Lot 5 : `database/poc/ISOLATED_DOCKER_BENCH.md`
- Lot 6 : `README.md`
- Lot 6 : `TODO.md`
- Lot 6 : `docs/architecture/overview.md`
- Lot 6 : `docs/quickstart/quickstart.md`
- Lot 6 : `docs/audit/CHECKPOINT_20261028_GIT_STATUS.txt`
- Lot 6 : `docs/audit/CHECKPOINT_20261028_PHASES_0_3.md`
- Lot 6 : `docs/audit/CHECKPOINT_20261028_REPRISE_GIT_STATUS.txt`
- Lot 6 : `docs/audit/CHECKPOINT_20261028_REPRISE_PHASES_0_3.md`
- Lot 6 : `docs/audit/PHASES_0_3_COVERAGE.md`
- Lot 6 : `docs/audit/README_ABOUT_PLAN.md`
- Lot 6 : `docs/audit/TODO_PHASES_0_3_20261028.snapshot.txt`
- Lot 6 : `docs/audit/TODO_PHASES_0_3_20261028_REPRISE.snapshot.txt`
- Lot 6 : `docs/audit/LOCAL_COMMITS_PHASES_0_3.md`

- Lot 6 : `.gitattributes`

## Inventaire complet des exports exclus et préservés

```text
database/poc/results/20261028-vm150-isolated-session/events.jsonl
database/poc/results/20261028-vm150-isolated-session/final/1000/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/1000/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/1000/restore.json
database/poc/results/20261028-vm150-isolated-session/final/1000/stage.json
database/poc/results/20261028-vm150-isolated-session/final/1000/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/1000/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/10000/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/10000/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/10000/restore.json
database/poc/results/20261028-vm150-isolated-session/final/10000/stage.json
database/poc/results/20261028-vm150-isolated-session/final/10000/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/10000/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/30/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/30/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/30/restore.json
database/poc/results/20261028-vm150-isolated-session/final/30/stage.json
database/poc/results/20261028-vm150-isolated-session/final/30/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated-session/final/30/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated-session/final/discovery/baseline.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated-session/final/discovery/discovery_qualification.json
database/poc/results/20261028-vm150-isolated-session/final/discovery/partial.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated-session/final/discovery/revision.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated-session/final/discovery/same-name-pair.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated-session/final/preflight.json
database/poc/results/20261028-vm150-isolated-session/final/resource_samples.json
database/poc/results/20261028-vm150-isolated-session/final/result.json
database/poc/results/20261028-vm150-isolated-session/final/versions.json
database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T165927Z-4831d4/result.json
database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170130Z-eff462/result.json
database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170315Z-d846b7/result.json
database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T170525Z-a923a3/result.json
database/poc/results/20261028-vm150-isolated-session/prior-attempts/attempt-20261028T171940Z-0545fe/result.json
database/poc/results/20261028-vm150-isolated-session/review-manifest.json
database/poc/results/20261028-vm150-isolated/events.jsonl
database/poc/results/20261028-vm150-isolated/final/1000/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/1000/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/1000/restore.json
database/poc/results/20261028-vm150-isolated/final/1000/stage.json
database/poc/results/20261028-vm150-isolated/final/1000/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/1000/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/10000/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/10000/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/10000/restore.json
database/poc/results/20261028-vm150-isolated/final/10000/stage.json
database/poc/results/20261028-vm150-isolated/final/10000/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/10000/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/30/postgres-indexes.sql
database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/30/postgresql-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/30/restore.json
database/poc/results/20261028-vm150-isolated/final/30/stage.json
database/poc/results/20261028-vm150-isolated/final/30/surreal-indexes.surql
database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-ingestion.json
database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-plan.json
database/poc/results/20261028-vm150-isolated/final/30/surrealdb-batch-receipts.jsonl
database/poc/results/20261028-vm150-isolated/final/discovery/baseline.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated/final/discovery/discovery_qualification.json
database/poc/results/20261028-vm150-isolated/final/discovery/partial.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated/final/discovery/revision.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated/final/discovery/same-name-pair.snapshot.synthetic.json
database/poc/results/20261028-vm150-isolated/final/preflight.json
database/poc/results/20261028-vm150-isolated/final/resource_samples.json
database/poc/results/20261028-vm150-isolated/final/result.json
database/poc/results/20261028-vm150-isolated/final/versions.json
database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T165927Z-4831d4/result.json
database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170130Z-eff462/result.json
database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170315Z-d846b7/result.json
database/poc/results/20261028-vm150-isolated/prior-attempts/attempt-20261028T170525Z-a923a3/result.json
database/poc/results/20261028-vm150-isolated/review-manifest.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/baseline.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/partial.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/discovery/revision.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/preflight.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/resource_samples.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/result.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204033Z-e34907/versions.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/baseline.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/partial.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/revision.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/discovery/surreal-import-error-31806168.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/preflight.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/resource_samples.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/result.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204222Z-f7c9c5/versions.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/baseline.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/discovery_qualification.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/partial.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/revision.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/discovery/same-name-pair.snapshot.synthetic.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/preflight.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/resource_samples.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/result.json
database/poc/results/20261028-vm150-replay-guard/attempt-20261028T204333Z-a15681/versions.json
database/poc/results/20261028-vm150-replay-guard/review-manifest.json
```
