# TODO v4 — Pepeuch AI Cluster

> Architecture directrice :
>
> **External Catalogs → Discovery Cache → Personal Model Catalog → Roles → Selector → Scheduler → Runtime → Workers → Agents → Workflows**
>
> Objectif : construire une plateforme IA locale et hybride capable de découvrir des modèles depuis plusieurs sources, ne conserver en profondeur que les modèles réellement pertinents pour les besoins de l'utilisateur, enrichir ces fiches avec les compatibilités matérielles et les benchmarks locaux, sélectionner dynamiquement le meilleur candidat, privilégier le calcul local et utiliser les providers distants uniquement en fallback contrôlé.

---

# Principes fondamentaux

- Le cluster ne doit **jamais dépendre d'un modèle nommé en dur**.
- Un workflow demande un **rôle**.
- Le selector choisit le modèle compatible.
- Le scheduler choisit où et quand exécuter le job.
- Le runtime manager choisit comment lancer le modèle.
- Les performances mesurées localement doivent progressivement remplacer les estimations.
- Le local est prioritaire.
- Les modèles payants/distants sont des fallbacks contrôlés.
- Les tâches destructives nécessitent une validation humaine.
- Les composants doivent rester modulaires, remplaçables et documentés.
- La base locale n'a pas vocation à recopier tout Hugging Face ou tout `models.dev`.
- Maintenir deux niveaux : **Discovery Cache** léger et **Personal Model Catalog** enrichi.
- Un modèle n'entre dans le catalogue personnel que s'il est potentiellement exploitable ou intéressant.
- `models.dev` sert de seed généraliste ; Hugging Face et NVIDIA servent surtout à enrichir les candidats.
- Chaque donnée importée doit conserver sa provenance et, si possible, la version/commit source.
- Les audits périodiques doivent être incrémentaux : comparer ce qui a changé, pas rescanner inutilement tout l'univers.


---

# Architecture cible

```text
models.dev (submodule / JSON / TOML)
Hugging Face API + repos modèles
NVIDIA NGC / Developer / NIM / TensorRT-LLM
OpenAI / Mistral / autres providers
                │
                ▼
        Model Discovery Service
                │
                ▼
          Discovery Cache
   (index léger, beaucoup de modèles)
                │
       filtres / règles / audit
                ▼
       Personal Model Catalog
      (uniquement modèles utiles)
                │
     ┌──────────┼───────────────┐
     │          │               │
 metadata   compatibilité   benchmarks locaux
     │          │               │
     └──────────┼───────────────┘
                ▼
            Model Selector
                │
       roles / policies / overrides
                │
                ▼
             Scheduler
                │
        ┌───────┼────────┐
        │       │        │
     Runtime  Runtime  Runtime
      local    local    remote
        │       │        │
        ▼       ▼        ▼
     A2000    4060    5060 Ti / API
        │
        └───────┼────────┘
                ▼
              Agents
                │
                ▼
            Workflows métier
```

---

# Phase 0 — Fondation du repository

## Déjà réalisé

- [x] Créer le repository GitHub
- [x] Choisir le nom : **Pepeuch AI Cluster**
- [x] Choisir la licence : **Apache-2.0**
- [x] Créer `README.md`
- [x] Créer `LICENSE`
- [x] Créer l'arborescence initiale
- [x] Créer `docs/concepts.md`
- [x] Définir node, worker, model, agent, role, workflow, job, resource profile
- [x] Établir la règle : **workflow → role**, jamais workflow → modèle fixe
- [x] Créer le schéma global d'architecture
- [x] Créer le quickstart initial
- [x] Préparer le script de création de VM Proxmox
- [x] Préparer le script d'installation NVIDIA dans la VM
- [x] Préparer un premier squelette de stack serveur

## À adapter à la v2

- [x] Réorganiser le repository selon la nouvelle architecture
- [x] Déplacer les anciens fichiers utiles
- [x] Archiver les prototypes devenus obsolètes
- [x] Mettre à jour README et architecture
- [x] Remplacer l'ancienne TODO par cette TODO v4

---

# Phase 1 — Infrastructure minimale du serveur

- [ ] Créer la VM via le script Proxmox
- [x] Vérifier réseau / stockage / SSH
- [ ] Passer la RTX A2000 en passthrough
- [ ] Vérifier `lspci`
- [ ] Installer le driver NVIDIA
- [ ] Vérifier `nvidia-smi`
- [ ] Installer NVIDIA Container Toolkit
- [ ] Vérifier le GPU depuis Docker
- [x] Installer / valider Docker Compose
- [x] Créer `/opt/pepeuch-ai`
- [ ] Définir volumes persistants
- [ ] Définir sauvegarde de la VM
- [ ] Ajouter healthchecks de base

**Checkpoint VM 150 — 27 octobre 2026**

- [x] Recycler manuellement la VM 150 en nœud `pepeuchai` (Debian 13 minimal) ; le script de création Proxmox reste à valider séparément.
- [x] Installer Docker Engine 29.9.2, Compose v5.6.1 ; `hello-world` réussi, service actif et activé au démarrage.
- [x] Préparer `/opt/pepeuch-ai/{repo,config,data,logs,backups}`.
- [x] Créer le volume Docker `pepeuch-ai-poc_postgres_data` et confirmer la persistance d'une donnée après redémarrage de PostgreSQL.
- [x] Configurer le stockage persistant SurrealDB/RocksDB (`/opt/pepeuch-ai/data/surreal-poc`) et confirmer les 405 modèles après redémarrage.
- [x] Corriger le healthcheck SurrealDB (`/surreal is-ready`) ; conteneur `Healthy`.
- [x] Limiter le cache RocksDB à 512 Mio (`SURREAL_ROCKSDB_BLOCK_CACHE_SIZE=536870912`) et les tampons d'écriture du POC.
- [ ] Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables.
- [ ] Vérifier les healthchecks de l'ensemble des services (SurrealDB confirmé `Healthy` ; état `healthy` de PostgreSQL encore à confirmer).
- [ ] Reprendre le passthrough RTX A2000 : échec VFIO/FLR (`stuck in D3`), validation GPU dans la VM reportée ; ne pas bloquer le POC CPU.

**Jalon :** un conteneur Docker peut utiliser correctement l'A2000.

**Checkpoint B3.1 — 27 octobre 2026 (ModelScope POC validé)**

- [x] Créer un adaptateur ModelScope `model_artifact` indépendant de Hugging Face, utilisant le SDK officiel `modelscope-hub==0.4.0`.
- [x] Valider les métadonnées, identités, licences, restrictions d'accès et valeurs inconnues avec une fixture synthétique et une requête réelle.
- [x] Exécuter 62/62 tests Python sur la VM.
- [x] Sonder réellement `Qwen/Qwen3-0.6B` : accès public, licence Apache-2.0, métadonnées normalisées et provenance préservée.
- [x] Importer le snapshot réel dans PostgreSQL et SurrealDB : 12 ressources par moteur, réimportation idempotente et 405 modèles historiques conservés.
- [ ] Étendre les sondes à plusieurs modèles et formats ; vérifier les révisions, fichiers, relations et éventuelles restrictions d'accès. L'API sondée ne fournit pas de SHA Git exploitable.

**Checkpoint B3.2 — 27 octobre 2026 (OpenCSG/CSGHub POC validé)**

- [x] Identifier l'API officielle CSGHub et distinguer les dépôts de modèles de la passerelle d'inférence.
- [x] Développer un adaptateur `model_artifact` indépendant de Hugging Face et ModelScope, avec identité et provenance propres.
- [x] Valider 76/76 tests Python sur la VM, dont 14 tests spécifiques à CSGHub.
- [x] Sonder réellement `OpenCSG/csg-wukong-1B` : SHA Git complet, 9 fichiers référencés et format Safetensors observé.
- [x] Préserver les métadonnées inconnues : licence non vérifiée et autorisation de téléchargement non déduite de la visibilité publique.
- [x] Importer et réimporter les métadonnées dans PostgreSQL et SurrealDB : 13 ressources par moteur, sans doublon et avec les 405 modèles historiques préservés.
- [ ] Étendre les sondes à d'autres dépôts et étudier séparément les ressources datasets, spaces, MCP, skills et les modèles servis par l'AI Gateway.

**Checkpoint B3.3 — 27 octobre 2026 (MoArk POC validé sur la VM Debian 13)**

- [x] Étudier l'OpenAPI officielle MoArk et les conditions d'accès ; distinguer Serverless, workflows et dépôts Git/LFS de modèles/datasets.
- [x] Ajouter un adaptateur `SourceRecord` de type `inference_endpoint`, sans fusion interplateforme ni preuve de poids déduite du catalogue.
- [x] Valider 91/91 tests Python localement et sur la VM, dont 15 tests MoArk sur fixture synthétique et client HTTP simulé.
- [x] Sonder réellement `Qwen3-8B` par un GET public anonyme ; conserver timestamp, provenance et inconnues, sans inférence.
- [x] Valider le snapshot B2 réel et ses imports PostgreSQL/SurrealDB ; voir [MOARK_B3.md](database/poc/MOARK_B3.md).
- [x] Importer puis réimporter sur la VM : 14 ressources par moteur, réimportation idempotente confirmée et 405 modèles historiques PostgreSQL préservés (résultats VM communiqués par l'utilisateur).
- [ ] Synchroniser les fichiers locaux non suivis de la VM avec la branche publiée, après comparaison ; voir [la procédure ciblée](database/poc/MOARK_VM_SYNC.md).
- [ ] Étudier séparément capacités, quotas applicables et dépôts de poids MoArk/Gitee ; aucune association automatique par nom.

Le connecteur est opérationnel pour les métadonnées publiques en lecture seule.
L'accès réel à l'inférence n'a pas été testé. Le Discovery Service automatisé
reste à développer ; ces validations portent sur des sondes et imports manuels.

**Checkpoint B4.0 — 27 octobre 2026 (contrats caractérisés, sans changement métier)**

- [x] Documenter la matrice des sept connecteurs, leurs identités, sélections, révisions, accès, inconnues, provenance, relations et transports ; voir [CONTRACTS_B40.md](database/poc/CONTRACTS_B40.md).
- [x] Extraire les références littérales du commit publié B3.3 : sept SourceRecord, clés B2, empreintes de payload, snapshots déterministes et comparaison partielle ; aucun attendu recalculé automatiquement par les tests.
- [x] Valider 108 tests, dont 17 tests de caractérisation ; conserver les sorties B2/B3 et les 91 tests historiques, sans réseau ni modification de base.
- [x] Caractériser NIM : identité par resourceId, tag mutable en révision, plusieurs tags du même service refusés dans un snapshot ; aucune modification de cette règle.
- [ ] Décider la sémantique future des accès/visibilités, de l'isolation domaines/comptes, des révisions et des collectes partielles avant toute évolution de format ou d'identité.
- [x] Consolider les primitives sans changer les snapshots de référence : secrets récursifs, copie défensive, parsing JSON et erreurs sûres ; voir [B4_JOURNAL.md](database/poc/B4_JOURNAL.md).

**Checkpoint B4.1 — 27 octobre 2026 (primitives communes validées)**

- [x] Mutualiser seulement les validations équivalentes ; conserver les règles métier, signatures et CLI des sept sources.
- [x] Copier défensivement SourceRecord, payloads et scopes ; rejeter récursivement les clés de credentials et décoder le JSON sans doublons ni valeurs non finies.
- [x] Normaliser les diagnostics sans corps d'erreur ni valeur sensible ; préserver le cas NIM 404.
- [x] Valider 122 tests et toutes les références B3.3 inchangées ; voir [PRIMITIVES_B41.md](database/poc/PRIMITIVES_B41.md).
- [x] Préparer le transport borné injectable sans retry et l'interface SDK, sans scheduler ni nouvelle collecte automatique.

**Checkpoint B4.2 — 27 octobre 2026 (transport borné préparé et partiellement intégré)**

- [x] Ajouter le client HTTP GET injectable : limites, timeout, allowlist HTTPS, refus des redirections, erreurs sûres et JSON strict ; aucun retry.
- [x] Migrer CSGHub/MoArk avec équivalence des requêtes et fixtures ; préparer l'interface SDK ModelScope sans réimplémenter son protocole ni importer le SDK au démarrage.
- [x] Valider 138 tests, les sept références B3.3 et les sorties des trois CLI B3 ; imports PG/SurrealDB générés identiques à B3.3, sans accès base.
- [ ] Décider et tester la politique de redirections B1 avant sa migration ; préserver le cas NIM 404 et les limites du SDK. Voir [TRANSPORT_B42.md](database/poc/TRANSPORT_B42.md).
- [x] Préparer l'interface du registre explicite des sept sources, sans collecte ni dépendance optionnelle au démarrage.

**Préparation B4.3 — 27 octobre 2026 (SourceSpec à examiner)**

- [x] Proposer SourceSpec/TransportSpec et une table déclarative des sept sources ; aucun binding CLI, chargement de plugin ou moteur de collecte.
- [x] Tester les types, sélections, révisions, capacités, immutabilité et absence de chargement de SDK/adaptateur/réseau à l'import ; 146 tests au total.
- [x] Documenter les limites réelles B1/SDK et les frontières Discovery Cache / fournisseurs d'inférence / Personal Model Catalog ; voir [SOURCE_SPEC_B43.md](database/poc/SOURCE_SPEC_B43.md).
- [ ] Examiner le prototype et décider multitag NIM, namespaces domaines/comptes, provenance synthétique/réelle et conventions de collecte partielle avant un registre opérationnel.
- [x] Relier les sept sources à un registre manuel sur fixtures ; budgets, retry, checkpoints et collecte planifiée restent hors de cette préparation.

**Checkpoint B4.3 — 27 octobre 2026 (registre et CLI manuelle sur fixtures)**

- [x] Tester et normaliser la lecture HTTP interrompue : stream fermé, corps partiel ignoré, erreur sûre et aucun retry.
- [x] Relier les sept normaliseurs au registre SourceSpec, avec imports tardifs, sélection/provenance explicites et contrôle des types et identités de sortie.
- [x] Ajouter `discover_sources.py --fixtures` et `--list-sources`, sans mode online ni import en base ; voir [DISCOVERY_B43.md](database/poc/DISCOVERY_B43.md).
- [x] Valider 167 tests sur fixtures uniquement ; sept snapshots et agrégat identiques aux références B3.3, CLI historiques préservées et aucune collecte réelle.
- [ ] Examiner le registre manuel avant toute extension online ; provenance synthétique/réelle, domaines/comptes, NIM multitag et résultats partiels restent à décider.

**Checkpoint B4.4 — 27 octobre 2026 (budgets et reprises validés hors ligne)**

- [x] Ajouter les politiques explicites par source/ressources : requêtes, tentatives, temps monotone total, plafond de délai et idempotence ; aucune valeur présentée comme quota fournisseur.
- [x] Classer les erreurs sans contenu sensible ; préserver NIM 404, interdire les retries 401/403/404/304 et erreurs de contrat ; aucune suppression.
- [x] Ajouter backoff exponentiel saturant, jitter et horloges injectés, Retry-After secondes/dates HTTP validés ; reporter sans attendre si budget/plafond insuffisant. Transport toujours à une tentative.
- [x] Produire des résultats indépendants et manifestes hors payload B2 ; aucun snapshot après échec, dépassement ou sélection incomplète. Aucune CLI réelle activée.
- [x] Préparer la protection synthétique optionnelle `--protected-output`, refusée avant SQL par les importeurs B2 existants, sans changer le mode brut historique ; voir [EXECUTION_B44.md](database/poc/EXECUTION_B44.md).
- [x] Valider 229 tests, dont les 167 précédents inchangés ; snapshots des sept sources et empreintes B3.3 conservés, aucune attente/réseau/base réels dans les tests.
- [ ] Décider la provenance obligatoire et le contrat d'import avant toute protection complète du B2 brut ; l'option ne remplace pas une validation d'origine.
- [x] B4.4 publié : `8ce3a8a23eecf4813c467e01c0c67d08b1eb839d`, référence distante vérifiée.

**Checkpoint B4.5 — 27 octobre 2026 (primitives locales, intégration différée)**

- [x] Lier provenance synthétique/contrôlée/historique inconnue au snapshot complet sans changer B2 ; attestation locale distincte d'une preuve fournisseur.
- [x] Ajouter une API opt-in de génération SQL protégée, refusant synthétique/inconnu/non approuvé ; aucun import réel ni changement des générateurs historiques.
- [x] Valider un cache au scope, ressources, domaine, partition de compte et révisions exacts ; revalidation 304 injectée, tag NIM toujours mutable.
- [x] Persister des checkpoints POSIX atomiques privés, intégrité, restauration de génération explicite, refus des écrivains concurrents et aucune purge automatique ; voir [CHECKPOINTS_B45.md](database/poc/CHECKPOINTS_B45.md).
- [x] Valider 272 tests hors ligne, dont 43 nouveaux ; sept sources et références B3.3 inchangées, aucune collecte réelle ni base.
- [ ] Définir l'enrôlement/rotation/révocation des émetteurs et la CLI protégée ; HMAC local ne prouve pas une collecte distante.
- [ ] Raccorder les reçus HTTP conditionnels au moteur budgété, la reprise inter-sources et les politiques de fraîcheur avant de déclarer B4.5 opérationnel.
- [ ] Définir pagination distante, garanties/quotas SDK, concurrence par hôte et budget global dans des lots séparés ; aucun scheduler.

---

# Phase 2 — Choix et POC de la base de données

Objectif : choisir le moteur de données avant de figer le schéma.

**Checkpoint expérimental — 27 octobre 2026**

- [x] Démarrer PostgreSQL 16.15 (`postgres:16-alpine`) via Compose, sur un réseau interne sans port publié.
- [x] Valider la connexion SQL, l'écriture et la lecture après redémarrage du conteneur.
- [x] Préparer le schéma `poc.external_models` et l'importeur TOML → SQL/COPY avec provenance Git ; 2 tests PostgreSQL réussis.
- [x] Analyser les 405 TOML du submodule épinglé : 405 fichiers analysés, aucune erreur.
- [x] Générer le flux SQL et importer réellement les 405 fiches dans PostgreSQL ; 405 enregistrements confirmés.
- [x] Vérifier le volume PostgreSQL après recréation du conteneur ; sauvegarde `pg_dump` et restauration dans une base de test vérifiées.
- [x] Déployer SurrealDB 3.3.4/RocksDB via Compose avec réseau interne, stockage persistant et healthcheck corrigé.
- [x] Préparer l'importeur TOML → SurrealQL ; 3 tests supplémentaires réussis (5 tests Python au total), 405 `UPSERT` validés et importés.
- [x] Comparer les six compteurs PostgreSQL/SurrealDB : 405 modèles, 196 open weights, 397 contextes positifs, 8 nuls, 154 poids, 135 benchmarks.
- [x] Confirmer les 405 modèles SurrealDB après redémarrage ; exporter et restaurer la sauvegarde dans `poc_restore_20261027`.
- [x] Valider la parité **14/14 requêtes en lecture seule** entre PostgreSQL et SurrealDB, y compris la régression `tool_call` / tool calling (349 modèles) ; ne pas assimiler les temps CLI/Docker à la latence du moteur.
- [ ] Comparer les moteurs sur les **mêmes requêtes représentatives**, index et mesures de performance ; aucun choix arrêté.

- [ ] Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation).
- [x] Importer un échantillon réel de `models.dev` dans les deux moteurs (ici les 405 TOML du snapshot épinglé).
- [ ] Tester les requêtes représentatives :
  - modèle → base model → quantification
  - modèle → provider → coût
  - modèle → runtime → GPU compatible
  - modèle → rôle candidat
  - modèle → benchmark local
- [ ] Tester la recherche vectorielle / hybride
- [ ] Tester relations de graphe et liens typés
- [x] Tester sauvegarde / restauration sur les deux POC, dans des bases distinctes des sources.
- [ ] Tester Docker et consommation mémoire
- [ ] Vérifier précisément les contraintes de licence de SurrealDB avant adoption
- [ ] Décider du moteur principal
- [ ] Documenter la décision

Tables / entités logiques à couvrir, quel que soit le moteur :

```text
providers
external_models
models
model_variants
model_capabilities
model_runtimes
model_licenses
model_sources
model_benchmarks
model_hardware_tests
nodes
workers
jobs
roles
role_requirements
selection_history
audit_runs
benchmark_suites
benchmark_cases
```

**Jalon :** un moteur de données est choisi sur des tests concrets et peut stocker un modèle, ses variantes, relations, runtimes et benchmarks.

# Phase 3 — Sources externes & Model Discovery

Objectif : exploiter les catalogues existants au lieu de reconstruire leur travail.

**Checkpoint B1 / B1.1 — 27 octobre 2026 (contrats et sondes seulement)**

- [x] Définir `SourceRecord` indépendant du moteur de base de données : source, identifiant externe, révision, type logique, attributs, relations explicites et métadonnées brutes.
- [x] Séparer `model_artifact` (Hugging Face), `agent_resource` (Awesome AI Agents) et `nim_microservice` (NVIDIA NIM) ; aucune identité canonique déduite d'un nom ressemblant.
- [x] Exécuter **33/33 tests Python** localement et sur la VM pour les contrats B1/B1.1 ; sonde NVIDIA réelle identique sur les deux environnements.
- [x] Fournir les sondes en lecture seule, sans modifier PostgreSQL/SurrealDB, télécharger de poids ni utiliser de GPU ou de clés privées (`database/poc/probe_source_adapters.py`).
- [ ] Industrialiser l'ingestion incrémentale (exécution planifiée, reprise sur erreur, rétention, surveillance) ; le POC B2 est une importation **manuelle**, pas encore un Discovery Service en production.

**Checkpoint B2 — 27 octobre 2026 (Discovery Cache POC validé sur la VM)**

- [x] Définir un snapshot JSON indépendant de PostgreSQL/SurrealDB, à identités stables `(source, entity_type, source_id)`, empreintes SHA-256, révisions, horodatages et périmètre de collecte.
- [x] Fournir les générateurs d'import `COPY`/upsert PostgreSQL et `UPSERT` SurrealDB, sans suppression automatique ni modification des tables historiques.
- [x] Valider sur la VM **48/48 tests Python**, puis deux imports initiaux à 5 ressources et leur réimportation idempotente (**5/5 dans les deux bases**).
- [x] Vérifier les comparaisons : même snapshot = **5 inchangées** ; simulation contrôlée = **1 ajoutée, 1 modifiée, 1 non observée, 3 inchangées**. `not_observed` n'autorise aucune suppression.
- [x] Collecter réellement **11 ressources** de `models.dev` (5), Hugging Face (2), Awesome AI Agents (3) et NVIDIA NIM (1) ; contrôler intégrité et identités ; importer **11/11** dans PostgreSQL et SurrealDB sans toucher aux 405 modèles historiques.
- [ ] Éprouver les imports partiellement échoués, les changements de révision réels et les variations de périmètre ; conserver les snapshots et définir la politique de rafraîchissement.

## 3.1 models.dev — source seed principale

- [x] Ajouter `anomalyco/models.dev` comme **git submodule**
- [x] Épingler un commit précis (`5e9fdbc3d88cb831627a93dc1362cc10773c176c`)
- [x] Enregistrer le SHA de source lors des imports PostgreSQL et SurrealDB du POC
- [ ] Exploiter prioritairement :
  - `models.json`
  - `catalog.json`
  - fichiers TOML `models/`
  - fichiers TOML `providers/`
- [ ] Créer un adapter/importer générique et indépendant du moteur de base de données
- [x] Préparer et valider l'importeur POC PostgreSQL (CSV/COPY + JSONB) ; 405 modèles réellement importés
- [x] Préparer et valider l'importeur POC SurrealDB (SurrealQL + métadonnées brutes) ; 405 modèles réellement importés
- [ ] Ne jamais faire dépendre le selector directement de leur format
- [ ] Détecter les deltas lors des mises à jour du submodule
- [ ] Conserver licence, provider, prix, contexte, modalités, reasoning, tool calling, structured output, open weights et liens vers poids/benchmarks

## 3.2 Hugging Face — enrichissement open-weight

- [x] Valider une **sonde publique ciblée** de l'API officielle sur `google/gemma-3-1b-it` (accès manuel, safetensors) et `ggml-org/gemma-3-1b-it-GGUF` (public, GGUF), avec SHA propres à chaque dépôt.
- [x] Normaliser dans le POC `gated`, licence, architecture, formats détectés, fichiers et relations `base_model` explicitement déclarées ; préserver `unknown` lorsque les métadonnées sont absentes.
- [ ] Étendre l'adaptateur à tous les champs pertinents ci-dessous, puis l'intégrer à la découverte sélective sans aspirer le Hub.
- [ ] Intégrer l'API officielle Hugging Face au Discovery Service (au-delà de la sonde B1)
- [ ] Ne pas aspirer tout le Hub
- [ ] Enrichir uniquement les candidats intéressants ou les familles utiles
- [ ] Récupérer :
  - model id / author
  - pipeline tag / tags
  - licence
  - base model
  - architecture
  - parameter count
  - context length
  - GGUF / safetensors
  - quantifications
  - fichiers
  - datasets
  - eval results
  - last modified
  - providers
- [ ] Détecter fine-tunes / LoRA / adapters / quantifications
- [ ] Relier les variantes au modèle parent
- [ ] Stocker provenance et niveau de confiance

## 3.3 NVIDIA Developer / NGC — enrichissement matériel

- [x] Valider une lecture **sans compte ni clé** de la NIM Metadata API v1.0.0 : `nim/nvidia/parakeet-1-1b-rnnt-multilingual:1.5.0`, 60 profils, dont 12 GPU-agnostic et 48 ciblant d'autres GPU que l'A2000.
- [x] Ajouter un contrat `nim_microservice` distinct des modèles et un screening conservateur RTX A2000 `2571:10de` / 12 Go / 1 GPU ; **60 profils sans VRAM minimale publiée**, donc aucun profil déclaré compatible ou validé en exécution.
- [x] Gérer les champs NVIDIA optionnels (`unknown` ≠ `false`), les futurs champs GPU chaîne/liste, et HTTP 404 comme absence de métadonnées **pour un tag**, non comme conteneur inexistant.
- [ ] Utiliser le compte NVIDIA Developer pour tester l'accès API hébergée et les droits NGC ; ne jamais versionner de clé (B1.1 est entièrement public et non authentifié).
- [ ] Ajouter authentification optionnelle NGC
- [ ] Gérer les niveaux d'accès :
  - public
  - compte developer requis
  - entitlement requis
  - inaccessible
- [ ] Rechercher pour chaque candidat :
  - NIM
  - TensorRT-LLM
  - vLLM CUDA
  - conteneur optimisé
  - FP16 / BF16
  - FP8
  - NVFP4
  - profils GPU
  - matériel supporté
- [ ] Relier les assets NVIDIA au modèle canonique
- [ ] Ne pas considérer NGC comme vérité canonique du modèle ; l'utiliser comme enrichissement d'optimisation

## 3.4 Providers distants

- [ ] Créer une abstraction provider générique
- [ ] OpenAI / Codex
- [ ] Mistral API éventuelle
- [ ] autres providers futurs
- [ ] Stocker coût, contexte, capacités, confidentialité et contraintes
- [ ] Distinguer modèle sous-jacent et provider qui le sert

## Hubs complémentaires à étudier — ModelScope, OpenCSG/CSGHub, MoArk

- [x] **ModelScope (Alibaba), POC B3.1** : adaptateur de métadonnées `model_artifact` et import manuel validés sur un dépôt ciblé, distinct de Hugging Face. L'extension à d'autres modèles, fichiers, datasets, Studios et agents reste à étudier.
- [x] **OpenCSG / CSGHub, POC modèles B3.2** : API officielle, adaptateur `model_artifact` et import manuel validés sur un dépôt ciblé, sans fusion interplateforme. Les ressources d'agents, datasets, spaces, MCP, skills et l'AI Gateway restent à étudier.
- [x] **MoArk (OSChina), POC B3.3** : catalogue public qualifié, adaptateur `inference_endpoint` et import manuel validés. L'inférence n'a pas été testée ; les dépôts de poids nécessitent un contrat séparé et une provenance vérifiée.
- [ ] Tester chaque connecteur sur des fixtures, avec conservation de la provenance, des valeurs inconnues et des limites de quotas ; aucune aspiration globale ni jeton stocké dans Git.

## Catalogue distinct de ressources d'agents (Awesome AI Agents)

- [x] Sonder le JSON officiel au commit épinglé `a32e86f60db8dd9556218403532264e0794822c4` : 305 entrées brutes, **304 IDs uniques**, un doublon strictement identique.
- [x] Normaliser les `agent_resource` et dédupliquer les doublons identiques ; refuser un même ID associé à des contenus divergents.
- [ ] Décider quelles ressources d'agents conserver dans un index séparé, sans les mélanger aux modèles d'inférence.

**Jalon :** le système peut importer `models.dev`, enrichir un candidat via Hugging Face et NVIDIA, puis produire une fiche normalisée.

# Phase 3.5 — Discovery Cache & Personal Model Catalog

Objectif : ne pas transformer la base locale en miroir géant.

## Discovery Cache

- [x] Valider un **POC d'import mult_sources** dans PostgreSQL et SurrealDB (11 ressources distinctes), avec identité stable et horodatage de dernière observation.
- [ ] Stocker un index léger des modèles externes vus
- [ ] Conserver au minimum :
  - external id
  - source
  - family
  - last seen
  - last modified
  - open/closed weights
  - candidate flag
  - ignore/reject reason éventuel
- [ ] Éviter de stocker les métadonnées lourdes pour les modèles non pertinents

## Personal Model Catalog

- [ ] Créer une fiche enrichie seulement pour les modèles utiles
- [ ] Ajouter statuts :
  - discovered
  - candidate
  - testing
  - adopted
  - fallback
  - watch
  - rejected
  - deprecated
- [ ] Ajouter marqueurs personnels :
  - usable_by_me
  - fits_my_hardware
  - nvidia_preferred
  - local_possible
  - paid_fallback
  - tested_locally
  - downloaded
  - production_ready
- [ ] Associer chaque modèle aux rôles potentiels
- [ ] Conserver raison d'adoption/rejet
- [ ] Conserver historique de décision

**Jalon :** le selector travaille sur le catalogue personnel, pas sur l'ensemble brut des sources externes.

---

# Phase 4 — Normalisation

- [ ] Normaliser noms de modèles
- [ ] Normaliser licences
- [ ] Normaliser runtimes
- [ ] Normaliser formats
- [ ] Normaliser quantifications
- [ ] Normaliser tailles
- [ ] Normaliser context lengths
- [ ] Normaliser architectures
- [ ] Normaliser capacités
- [ ] Dédupliquer les variantes
- [ ] Relier base model / fine-tune / LoRA / quantification / fork
- [ ] Ajouter niveau de confiance par information

Exemple :

```text
official_metadata = 1.0
config_detected   = 0.9
model_card_parsed = 0.7
community_tag     = 0.5
unknown           = 0.0
```

---

# Phase 4.5 — Model Lifecycle & Audits périodiques

Objectif : maintenir le catalogue pertinent sans travail manuel permanent.

## Bootstrap initial

- [ ] Lancer un premier audit large des sources
- [ ] Construire le Discovery Cache
- [ ] Filtrer selon les domaines réellement utiles
- [ ] Construire la première shortlist
- [ ] Enrichir les meilleurs candidats
- [ ] Tester les candidats prioritaires
- [ ] Classer ADOPT / TEST / WATCH / REJECT

## Audit périodique

Cadence initiale :

```text
quotidien    → santé cluster uniquement
hebdomadaire → refresh metadata léger si nécessaire
mensuel      → audit catalogue + nouveaux candidats + benchmarks ciblés
```

- [ ] Comparer avec le dernier audit
- [ ] Identifier uniquement :
  - nouveaux modèles
  - nouvelles versions
  - nouvelles quantifications
  - nouveaux runtimes
  - nouvelles optimisations NVIDIA
  - changements de prix/provider
- [ ] Générer une shortlist de candidats à tester
- [ ] Ne benchmarker que les modèles prometteurs
- [ ] Produire un rapport mensuel

## Golden tasks / projets de référence

- [ ] Créer des jeux de tests maison versionnés
- [ ] `filesystem_reference`
- [ ] `media_reference`
- [ ] `repo_review_reference`
- [ ] `infra_logs_reference`
- [ ] `pcb_reference` plus tard
- [ ] Mesurer qualité + performance + coût
- [ ] Conserver les résultats historiques
- [ ] Réexécuter les références lorsqu'un modèle/runtime/driver change

**Jalon :** un audit mensuel peut proposer automatiquement de nouveaux modèles et démontrer s'ils font réellement mieux sur les tâches de référence.

---

# Phase 5 — Roles & Policies

Créer :

```text
config/
├── roles.yaml
├── policies.yaml
└── overrides.yaml
```

## Rôles H24

- [ ] filesystem-classification
- [ ] filesystem-embedding
- [ ] media-vision
- [ ] media-embedding
- [ ] infra-monitoring
- [ ] infra-log-analysis
- [ ] repo-light-review
- [ ] repo-indexing
- [ ] business-invoice-draft
- [ ] business-invoice-validation
- [ ] business-document-classification
- [ ] business-admin-assist

## Rôles temporaires

- [ ] infra-deep-analysis
- [ ] repo-heavy-audit
- [ ] pcb-schematic
- [ ] pcb-analysis
- [ ] pcb-placement
- [ ] pcb-routing
- [ ] pcb-review
- [ ] cad-assist
- [ ] business-regulation-check
- [ ] business-einvoice-export
- [ ] business-accounting-assist

## Policies

- [ ] `prefer_local: true`
- [ ] `prefer_free: true`
- [ ] `prefer_measured_performance: true`
- [ ] `prefer_nvidia_optimized: true`
- [ ] définir les licences autorisées
- [ ] définir les limites VRAM
- [ ] définir les limites de coût API
- [ ] définir les règles de confidentialité
- [ ] définir quand demander validation humaine
- [ ] définir la priorité des providers

## Overrides

- [ ] Forcer un modèle pour test
- [ ] Désactiver un modèle
- [ ] Bloquer une version
- [ ] Surclasser un benchmark
- [ ] Ajouter une note utilisateur

**Jalon :** les workflows ne référencent plus aucun modèle précis.

---

# Phase 6 — Model Selector

- [ ] Construire le moteur de sélection
- [ ] Filtrer selon rôle, licence, runtime, VRAM, RAM, GPU, contexte
- [ ] Filtrer local / remote
- [ ] Filtrer selon confidentialité
- [ ] Ajouter score matériel
- [ ] Ajouter score qualité
- [ ] Ajouter score runtime
- [ ] Ajouter score coût
- [ ] Ajouter score disponibilité
- [ ] Ajouter score benchmark local
- [ ] Privilégier mesures réelles aux estimations
- [ ] Ajouter fallbacks
- [ ] Conserver la raison du choix

Exemple :

```text
role: repo-heavy-audit

selected:
  model: X
  runtime: vllm
  node: workstation-5060ti

reason:
  - compatible role
  - VRAM suffisante
  - meilleur benchmark local
  - aucun coût API
```

---

# Phase 7 — Runtime Manager

Support progressif :

- [ ] llama.cpp
- [ ] Ollama
- [ ] Transformers
- [ ] vLLM
- [ ] TensorRT-LLM
- [ ] ONNX Runtime
- [ ] PyTorch spécifique
- [ ] provider API distant

Pour chaque runtime :

- [ ] détection disponibilité
- [ ] chargement
- [ ] healthcheck
- [ ] unload
- [ ] timeout
- [ ] métriques
- [ ] VRAM utilisée
- [ ] RAM utilisée
- [ ] durée de chargement
- [ ] throughput
- [ ] gestion des erreurs

**Jalon :** le selector choisit un modèle, le runtime manager sait le lancer.

---

# Phase 8 — Benchmark local

- [ ] Créer benchmark standardisé
- [ ] Mesurer load time
- [ ] Mesurer TTFT
- [ ] Mesurer tokens/s
- [ ] Mesurer VRAM peak
- [ ] Mesurer RAM peak
- [ ] Mesurer GPU utilization
- [ ] Mesurer power draw si disponible
- [ ] Associer résultat à modèle + quantification + runtime + GPU
- [ ] Stocker version driver/runtime
- [ ] Ajouter date et score de confiance
- [ ] Comparer plusieurs runtimes
- [ ] Comparer NVIDIA optimized vs portable
- [ ] Automatiser les benchmarks nocturnes
- [ ] Supporter les golden tasks métier en plus des micro-benchmarks
- [ ] Comparer qualité réelle, pas uniquement tokens/s

**Jalon :** le selector choisit selon les performances réellement mesurées sur notre matériel.

---

# Phase 9 — Jobs & Scheduler

États :

```text
queued
running
paused
completed
failed
cancelled
```

- [ ] priorité
- [ ] retries
- [ ] timeout
- [ ] dépendances
- [ ] logs
- [ ] résultats
- [ ] checkpoints
- [ ] tâches resumable
- [ ] fenêtres horaires
- [ ] tâches nocturnes
- [ ] tâches interactives
- [ ] préemption
- [ ] pause/reprise
- [ ] quotas
- [ ] limites thermiques
- [ ] limites de coût

Priorités initiales :

```text
100 interaction utilisateur
 80 incident infrastructure
 50 audit demandé
 20 classification
 10 indexation nocturne
  5 maintenance opportuniste
```

---

# Phase 10 — Nodes & Workers

## Serveur

- [ ] A2000 12 Go
- [ ] worker H24
- [ ] profil `always-on`

## Station

- [ ] SSD USB AI Node
- [ ] RTX 5060 Ti 16 Go
- [ ] profil `heavy`
- [ ] démarrage à la demande

## NUC9

- [ ] SSD USB AI Node
- [ ] RTX 4060 8 Go
- [ ] profil `light`

## Commun

- [ ] Resource profiles
- [ ] Capabilities
- [ ] Auto-join
- [ ] Healthchecks
- [ ] Gestion node indisponible

---

# Phase 11 — Ray

- [ ] Ray Head serveur
- [ ] A2000 worker permanent
- [ ] 5060 Ti worker
- [ ] 4060 worker
- [ ] custom resources
- [ ] jobs CPU
- [ ] jobs GPU
- [ ] contraintes VRAM
- [ ] attente si ressource absente
- [ ] fallback node
- [ ] dashboard

**Jalon :** un job soumis au serveur s'exécute automatiquement sur le bon node.

---

# Phase 12 — Fallback distant / payant

- [ ] Provider abstraction
- [ ] OpenAI / Codex
- [ ] autres providers éventuels
- [ ] budget par job
- [ ] budget journalier
- [ ] approval required
- [ ] règles de confidentialité
- [ ] redaction éventuelle
- [ ] jamais prioritaire sur un modèle local compatible
- [ ] conserver le coût réel dans les métriques

Flux :

```text
local model
   ↓ insuffisant
heavy local model
   ↓ indisponible / insuffisant
remote fallback
   ↓
validation humaine si payant
```

---

# Phase 13 — Agents H24

## Fichiers

- [ ] scan
- [ ] hash
- [ ] MIME
- [ ] métadonnées
- [ ] doublons exacts
- [ ] classification
- [ ] propositions de rangement
- [ ] aucun déplacement automatique au début

## Photos / vidéos

- [ ] EXIF
- [ ] hash
- [ ] embeddings
- [ ] doublons visuels
- [ ] OCR
- [ ] tags
- [ ] scènes
- [ ] intégration Immich plus tard

## Cluster / VM

- [ ] Proxmox read-only
- [ ] logs
- [ ] SMART
- [ ] stockage
- [ ] backups
- [ ] Docker
- [ ] updates proposées
- [ ] corrections proposées
- [ ] validation humaine avant write

## Git

- [ ] repo indexing
- [ ] bump detection
- [ ] issues
- [ ] PR review
- [ ] tests
- [ ] checkpoints
- [ ] propositions
- [ ] application manuelle

## Gestion administrative / facturation

Objectif : assister les micro-entreprises / freelances sans automatiser aveuglément les actes engageants.

- [ ] profils entreprise séparés
- [ ] base clients
- [ ] base prestations / tarifs
- [ ] génération de brouillons de facture
- [ ] vérification des champs obligatoires
- [ ] détection d'incohérences
- [ ] numérotation contrôlée
- [ ] classement des factures / justificatifs
- [ ] extraction OCR des documents reçus
- [ ] préparation des formats de facturation électronique
- [ ] préparation e-reporting si nécessaire
- [ ] suivi des statuts : brouillon / validée / envoyée / payée / en retard
- [ ] rappels d'échéance
- [ ] export comptable
- [ ] archivage
- [ ] validation humaine avant envoi
- [ ] aucune déclaration fiscale / sociale automatique sans validation explicite

---

# Phase 14 — Workflows temporaires

## Infrastructure réseau

- [ ] inventaire devices
- [ ] VLAN
- [ ] firewall
- [ ] configs
- [ ] analyse
- [ ] suggestions
- [ ] aucune modification sans validation

## PCB

- [ ] schematic
- [ ] analysis
- [ ] placement
- [ ] routing
- [ ] review
- [ ] KiCad MCP
- [ ] ERC/DRC
- [ ] benchmark modèles spécialisés
- [ ] Ailiance / SchGen / Mistral / Qwen / autres

## CAD

- [ ] définir besoins
- [ ] décider si pertinent
- [ ] rechercher modèles/outils
- [ ] garder optionnel tant que non justifié

## Business / facturation électronique

- [ ] définir un modèle de données entreprise
- [ ] définir profils micro-entreprise / freelance
- [ ] intégrer les règles métier sous forme de données versionnées
- [ ] préparer génération de facture structurée
- [ ] prévoir connecteur vers plateforme agréée / logiciel compatible
- [ ] journaliser chaque action proposée
- [ ] exiger validation humaine avant émission
- [ ] benchmarker les modèles sur :
  - extraction de facture
  - génération structurée
  - contrôle de cohérence
  - classement documentaire
  - synthèse administrative
- [ ] créer un `business_reference` comme golden task

---

# Phase 15 — Sécurité

Hiérarchie :

```text
READ        = automatique
ANALYZE     = automatique
PROPOSE     = automatique
WRITE       = contrôlé
DESTRUCTIVE = validation humaine obligatoire
```

- [ ] comptes dédiés
- [ ] sudo minimal
- [ ] secrets hors Git
- [ ] mounts read-only
- [ ] audit trail
- [ ] logs
- [ ] permissions par agent
- [ ] permissions par workflow
- [ ] permissions par provider
- [ ] confidentialité par rôle

---

# Phase 16 — UI / Observabilité

- [ ] dashboard cluster
- [ ] nodes online/offline
- [ ] GPU / VRAM
- [ ] jobs
- [ ] queues
- [ ] modèles chargés
- [ ] sélection expliquée
- [ ] coût API
- [ ] benchmarks
- [ ] healthchecks
- [ ] logs
- [ ] historique des décisions

---

# Phase 17 — Reproductibilité

- [ ] Ansible
- [ ] bootstrap serveur
- [ ] bootstrap worker
- [ ] profils GPU génériques
- [ ] migrations DB
- [ ] CI
- [ ] tests
- [ ] documentation
- [ ] upgrade path
- [ ] backup/restore
- [ ] release stable
- [ ] guide add provider
- [ ] guide add runtime
- [ ] guide add role
- [ ] guide add agent
- [ ] guide add worker

---

# MVP v2

```text
VM IA
  ↓
PostgreSQL
  ↓
Hugging Face Collector
  ↓
Model Catalog
  ↓
roles.yaml
  ↓
Model Selector
  ↓
llama.cpp / Ollama
  ↓
A2000
  ↓
filesystem-classification
  ↓
premier agent READ-ONLY
```

**Tant que ce chemin complet n'est pas stable, ne pas ajouter Ray, les workers externes ou les workflows PCB.**

---

# Ordre de développement

```text
1. Infrastructure
2. POC Database (PostgreSQL vs SurrealDB)
3. models.dev submodule + importer
4. Discovery Cache
5. Personal Model Catalog
6. Hugging Face enrichment
7. NVIDIA enrichment
8. Normalization
9. Roles / Policies
10. Selector
11. Runtime Manager
12. Local Benchmarks + Golden Tasks
13. Scheduler
14. Workers
15. Ray
16. Remote fallback
17. Agents H24
18. Workflows temporaires
19. Security hardening
20. UI / Observability
21. Reproducibility
22. Monthly Model Audit
```

---

# Règle finale

> **Les sources externes découvrent les possibilités.**
>
> **Le Discovery Cache mémorise ce qui existe.**
>
> **Le Personal Model Catalog conserve ce qui est utile.**
>
> **Les rôles décrivent le besoin.**
>
> **Le selector choisit le modèle.**
>
> **Le scheduler choisit le moment et la machine.**
>
> **Le runtime manager exécute.**
>
> **Les agents accomplissent la mission.**

> **L’utilisateur est content : il a économisé 10 employés.**
