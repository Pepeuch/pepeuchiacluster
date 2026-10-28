# Organisation et exécution des tests

Commandes depuis la racine du dépôt, sans benchmark, fournisseur, import DB,
GPU ou installation. Les tests HTTP utilisent loopback ; l’isolation applicative
ne qualifie pas un environnement OS réellement isolé.

## Toutes les suites

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_suites.py -q
```

Le lanceur crée un processus par suite, depuis la racine du dépôt, pour préserver
les helpers historiques `test_http_integration`, `test_contracts`, `fixtures`
sans collisions. Un échec rend son code retour non nul. Sans `-q`, chaque cas est
affiché. `--suite discovery` sélectionne une suite ; l’option peut être répétée.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.discovery -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/control_plane -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/infrastructure -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/isolation -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/worker -p 'test_*.py' -v
```

Discovery accepte aussi :

```bash
python3 -m unittest discover -s tests/discovery -t . -p 'test_*.py' -v
```

`unittest discover -s tests` seul n’est pas le lanceur global : les suites
historiques ne sont pas toutes des packages et leurs helpers ne sont pas encore
qualifiés pour un espace de modules partagé. Utiliser `tests/run_suites.py`.

## Migration progressive Discovery

`tests.discovery` charge sept modules déplacés, deux modules supplémentaires
(intégrité/CAS et provenance/HTTP), et vingt modules historiques.
Le relais `database/poc/test_discovery_consolidation.py` préserve la commande :

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -q
```

Les deux points d’entrée exposent **les mêmes 391 cas uniques**, sans doublon.
Le package ajoute le chemin du code `database/poc/`, sans modifier les adaptateurs.
Un module déplacé se cible par exemple ainsi :

```bash
python3 -m unittest tests.discovery.test_discovery_replay_guard -v
```

Le ciblage des sept nouveaux modules par leur ancien fichier dans `database/poc/`
n’est pas conservé. Aucun des vingt chemins de tests historiques n’est déplacé.

| Module | Cas | Emplacement / dépendances |
|---|---:|---|
| test_benchmark_readonly | 4 | POC conservé ; requêtes sans exécuter le benchmark |
| test_collect_discovery_snapshot | 3 | POC conservé |
| test_contract_reference_b40 | 17 | POC conservé ; fixtures relatives B3.3, helper partagé |
| test_csghub_adapter | 14 | POC conservé ; fixtures et CLI relatives |
| test_discovery_cache | 12 | POC conservé |
| test_discovery_registry | 18 | POC conservé ; CLI isolées, fixtures et helper partagé |
| test_execution_b44 | 48 | POC conservé ; fixtures relatives et FakeClock partagé |
| test_import_models_dev | 4 | POC conservé |
| test_import_models_dev_surreal | 3 | POC conservé |
| test_metadata_http | 19 | POC conservé |
| test_metadata_primitives | 14 | POC conservé ; test_contract_reference_b40 |
| test_moark_adapter | 15 | POC conservé ; CLI/fixtures, procédure de synchronisation VM |
| test_modelscope_adapter | 14 | POC conservé ; fixtures et CLI relatives |
| test_nvidia_nim_adapters | 9 | POC conservé |
| test_probe_source_adapters | 4 | POC conservé |
| test_recovery_b45 | 43 | POC conservé ; fixtures et test_execution_b44 |
| test_retry_after | 8 | POC conservé |
| test_source_adapters | 9 | POC conservé |
| test_source_spec_design | 8 | POC conservé ; subprocess isolé relatif au code testé |
| test_synthetic_output | 6 | POC conservé ; test_discovery_registry |
| test_comparison_workload | 9 | tests/discovery ; module de production inchangé |
| test_discovery_replay_guard | 8 | tests/discovery ; deux contrôles de preuves privées |
| test_incremental_import_plan | 9 | tests/discovery ; module de production inchangé |
| test_isolated_bench | 18 | tests/discovery ; Docker/clients simulés |
| test_isolated_bench_contracts | 13 | tests/discovery ; fixture observée masquée sous POC_ROOT |
| test_isolated_bench_results | 5 | tests/discovery ; preuves privées sous POC_ROOT |
| test_manual_discovery_run | 13 | tests/discovery ; FakeClock de test_execution_b44 |
| test_integrity_cas | 15 | tests/discovery ; contrats B2/CAS et génération SQL, aucune base réelle |
| test_conditional_provenance | 29 | tests/discovery ; fixture HTTP synthétique, horloge/transport injectés, registre éphémère et fichiers temporaires privés |

Les vingt anciens modules totalisent **272 cas**. Leur migration physique est
reportée : chemins `__file__`, helpers, procédures VM et points d’entrée nécessitent
un lot de compatibilité distinct. Le déplacement actuel ne change aucune assertion
ni référence ; comparaison AST des corps des tests et empreintes des fixtures vérifiées.

## Fixtures, preuves privées et exécutables

`database/poc/fixtures/` conserve toutes les fixtures B2/B3/B4, noms et références
littérales. Aucune duplication dans `tests/fixtures/` : ce futur emplacement attend
un besoin et une migration dédiée. Les deux fixtures nouvelles sont synthétique
(`comparison.synthetic.json`) et observée masquée (`surreal_explain_334.observed_sanitized.json`).

Les trois exports `database/poc/results/20261028-vm150-*` sont **privés, ignorés
par Git, conservés sans modification**. Voir [l’inventaire des exclusions](../docs/audit/LOCAL_COMMITS_PHASES_0_3.md).
Un quatrième dossier privé `20261028-vm150-cas/` conserve la qualification
fonctionnelle CAS distincte des benchmarks ; aucun de ces résultats n'est ajouté
au versionnement. La fixture additive `http_conditionals.synthetic.json` est
entièrement synthétique ; aucune clé, attestation ou donnée d'authentification.
La préparation de confidentialité rend sept contrôles de preuves privées
explicitement `skipped` si leur dossier est absent. Les assertions restent intactes ;
un dossier présent mais incomplet/corrompu échoue. Cette précondition est distincte
du déplacement et n’autorise aucune acquisition réseau.

Avec les exports locaux : **644 succès** (391 Discovery, 123 Control Plane,
19 infrastructure, 63 isolation applicative, 48 worker). Sans exports :
**637 succès et sept skipped**, sans nouvelle qualification de bases réelles.

Les exécutables `benchmark_readonly.py`, `isolated_docker_bench.py` et leurs
modules restent dans `database/poc/`, séparés du lanceur unittest.
`tests/browser_b51.py` est une validation navigateur explicite avec binaires
locaux ; elle reste hors des 644 tests et n’est pas relancée ici. Aucun pilote
négatif OS privilégié n’est activé.
