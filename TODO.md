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
- [x] Passer la RTX A2000 en passthrough
- [x] Vérifier `lspci`
- [x] Installer le driver NVIDIA
- [x] Vérifier `nvidia-smi`
- [x] Installer NVIDIA Container Toolkit
- [x] Vérifier le GPU depuis Docker
- [x] Installer / valider Docker Compose
- [x] Créer `/opt/pepeuch-ai`
- [x] Définir volumes persistants — Compose existants et montages VM150 confirmés le 28/10 ; voir la politique de stockage.
- [ ] Définir sauvegarde de la VM
- [x] Ajouter healthchecks de base — configuration et cinq dernières sondes de chaque base confirmées en lecture seule ; bases actuellement arrêtées, disponibilité courante non validée.

**Checkpoint VM 150 — 27 octobre 2026**

- [x] Recycler manuellement la VM 150 en nœud `pepeuchai` (Debian 13 minimal) ; le script de création Proxmox reste à valider séparément.
- [x] Installer Docker Engine 29.9.2, Compose v5.6.1 ; `hello-world` réussi, service actif et activé au démarrage.
- [x] Préparer `/opt/pepeuch-ai/{repo,config,data,logs,backups}`.
- [x] Créer le volume Docker `pepeuch-ai-poc_postgres_data` et confirmer la persistance d'une donnée après redémarrage de PostgreSQL.
- [x] Configurer le stockage persistant SurrealDB/RocksDB (`/opt/pepeuch-ai/data/surreal-poc`) et confirmer les 405 modèles après redémarrage.
- [x] Corriger le healthcheck SurrealDB (`/surreal is-ready`) ; conteneur `Healthy`.
- [x] Limiter le cache RocksDB à 512 Mio (`SURREAL_ROCKSDB_BLOCK_CACHE_SIZE=536870912`) et les tampons d'écriture du POC.
- [ ] Définir et vérifier une sauvegarde/restauration Proxmox de la VM 150 avant d'y stocker des données irremplaçables.
- [ ] Confirmer la disponibilité courante des healthchecks des deux bases après autorisation : cinq dernières sondes de chaque base réussies avant l’arrêt, mais conteneurs actuellement arrêtés ; aucun démarrage autorisé.
- [x] Résoudre le blocage VFIO/FLR (`stuck in D3`) constaté le 27 octobre : passthrough et GPU Docker validés par l’utilisateur le 28 octobre ; voir le checkpoint ci-dessous.

**Checkpoint GPU VM150 — 28 octobre 2026 (rapport utilisateur)**

**VERIFIED** : Proxmox VE 9.2, Debian 13, A2000 12 Go/VFIO, hôte sur iGPU Intel,
BIOS ASUS PRIME Z790M-PLUS D4 1836, NVIDIA 615.71.10, Secure Boot/MOK,
Toolkit 1.20.1 et Docker 29.9.2. `lspci`, `nvidia-smi` (12 282 MiB), programme
CUDA Debian de 256 threads/256 résultats corrects et GPU visible dans Docker.
[Preuves, provenance et limites](docs/infrastructure/VM150_GPU_20261028.md).
**NOT VERIFIED** : CUDA dans Docker, inférence, charge prolongée et isolation OS.
Les six cases GPU et le doublon historique VFIO sont clôturés sur ces preuves,
sans nouvelle intervention système. Les essais VM script/backup/restore restent
**BLOCKED** faute d’environnement jetable autorisé et de GO d’accès Proxmox.

**Audit phases 0–3, arrêt avant 3.1 — 28 octobre 2026**

[Inventaire exhaustif initial et dépendances](docs/audit/PHASES_0_3_COVERAGE.md) :
49 cases ouvertes avant ce lot (0/38/9/2 par phase), dont 9 lignes clôturées :
six GPU, résolution VFIO, volumes persistants et ajout des healthchecks de base.
Leur readiness historique est prouvée, leur disponibilité courante reste ouverte.
Travail sur `feat/todo-phases-0-3`, `main` préservé.
Le plan VM et les tests locaux sont **IMPLEMENTED / TESTED**, pas une création
Proxmox **VERIFIED**. Après échec initial des clés, accès VM150 réussi avec le
mot de passe explicitement fourni, limité à cette VM : GPU/versions/montages
confirmés. **Les deux bases sont arrêtées** (`Exited (0)`, health mémorisé
`unhealthy`) ; aucun démarrage ni requête SQL. Proxmox reste inaccessible par
la clé essayée ; aucun essai de mot de passe sur cet hôte, agent QEMU ou changement
d’authentification. [Inventaire réel](docs/infrastructure/VM150_READONLY_20261028.md),
[stockage et GO nécessaires](docs/infrastructure/STORAGE_AND_VALIDATION.md).
Après ce lot local, 40 cases restaient ouvertes ; le banc isolé ci-dessous en clôture
ensuite cinq, soit **35 restantes** avant 3.1. Aucun POC historique modifié.
Aucun accès supplémentaire à Proxmox autorisé ; bases conservées arrêtées.

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

**Étude B5.0 — 27 octobre 2026 (branche documentaire indépendante)**

- [x] Partir de B4.4 publié `8ce3a8a23eecf4813c467e01c0c67d08b1eb839d` ; aucun code B4.5 fusionné, aucun push B5.
- [x] Proposer backend autonome, UI minimale libre, conversation distincte du coordinateur, contrats de rôles/selector/scheduler/runtime/worker et progression avant premier agent ; voir [WEBUI_CONTROL_PLANE.md](docs/architecture/WEBUI_CONTROL_PLANE.md).
- [x] Étudier les sources officielles Open WebUI/AnythingLLM : restriction de marque Open WebUI 0.6.6+, code AnythingLLM MIT mais conditions Desktop distinctes ; API optionnelles recommandées, aucun fork ; voir [OPEN_WEBUI_ANYTHINGLLM_STUDY.md](docs/architecture/OPEN_WEBUI_ANYTHINGLLM_STUDY.md).
- [x] Comparer VM serveur Proxmox, compagnon Windows/macOS/Linux volontaire et USB disque/live ; définir appairage, LAN non fiable, inventaire, consentement et limites de partage ; voir [NODE_PROVISIONING_DESIGN.md](docs/architecture/NODE_PROVISIONING_DESIGN.md).
- [x] Définir workspace durable, transferts, versions, permissions, reprise et archives indépendants du conteneur/worker ; voir [WORKSPACE_MANAGER_DESIGN.md](docs/architecture/WORKSPACE_MANAGER_DESIGN.md).
- [ ] Valider les contrats d'identité/appairage/bail et l'API de mission avant B5.1 ; développer un faux worker puis autoriser séparément un pilote Linux CPU.
- [ ] Choisir langage/packaging, stockage durable et politique de clés ; vérifier licences/artefacts exacts, notamment Desktop avant toute redistribution.
- [ ] Établir une matrice réellement testée par OS/runtime ; aucune capacité GPU/inférence/agent annoncée comme vérifiée par cette étude.
- [ ] Garder interfaces tierces, VM automatisée, compagnon multi-OS et USB dans des lots séparés ; aucune installation/provisionnement/migration effectués dans B5.0.

---

**Checkpoint B5.1 — 27 octobre 2026 (prototype local, exécution simulée)**

- [x] Développer sur `feat/webui-control-plane-b51` depuis `main` / `a4cb141`, trois merges vérifiés ; commits locaux seulement.
- [x] B5.1a : API versionnée loopback, identité locale contrôlée, rôles admin/worker distincts, missions et audit SQLite séparés, migration explicite, idempotence et permissions propriétaire/projet.
- [x] B5.1b : approbation explicite, plan et tâche, capacité déclarée de démonstration, worker séparé, tentatives bornées, annulation, expiration, résultats tardifs et reprise manuelle ; aucune IA réelle.
- [x] B5.1c : fichiers versionnés immuables, staging/intégrité/publication durable, upload/download bornés, quotas et conflits concurrents ; résultat et historique conservés après redémarrage.
- [x] B5.1d : trois sections WebUI responsive, formulaire et brouillon, confirmation d'envoi, suivi, fichiers autorisés et livrables ; ressources locales, pas de cookies/CDN.
- [x] Valider 69 tests B5.1 et un parcours Firefox complet, worker séparé et redémarrage inclus ; conserver les 272 tests Discovery Cache sans modification. Voir [B51_IMPLEMENTATION.md](docs/architecture/B51_IMPLEMENTATION.md).
- [ ] Finaliser la pile HTTP de production et l'isolation OS d'un vrai worker ; les contrôles locaux HTTP/identité/sauvegarde sont validés au checkpoint B5.2, sans exposition LAN.
- [ ] Définir les contrats agents/rôles/baux réels, appairage/TLS et politiques multi-utilisateurs avant une ouverture LAN ou exécution d'outils ; aucune installation, inférence ou collecte réelle dans B5.1.

**Checkpoint B5.2 — 27 octobre 2026 (sécurité et résilience locales)**

- [x] Partir de `main` actualisé (`a822b4d`, B5.1 mergé), sur `feat/webui-control-plane-b52` ; commits locaux par lot, aucun push ni merge B5.2.
- [x] B5.2a : cadrage HTTP strict, limites des lignes/en-têtes/corps/connexions, deadlines absolues de lecture, réponses sans secrets ni cache ; sous-ensemble loopback, pas de validation production.
- [x] B5.2b : sauvegarde cohérente hors ligne et restauration dans une destination inexistante, schéma/FK/références/SHA256 vérifiés, secrets exclus et clés renouvelées ; interruptions/corruptions testées, aucune purge automatique.
- [x] B5.2c : registre d'identités stable, capacités de démonstration fermées, rotation hors ligne et révocation en ligne ; autorisation transactionnelle, epochs de credentials et refus des anciens résultats. Migration applicative B5.1 compatible.
- [x] Préparer séparément [l'isolation OS](docs/architecture/WORKER_ISOLATION_B52.md) ; aucun UID, conteneur, montage ou quota CPU/RAM appliqué dans ce lot.
- [x] B5.2d : 395 tests Python réussis (272 Discovery + 123 Control Plane, dont les 341 initiaux inchangés), scénario Firefox B5.1 rejoué, restauration et anciens formats vérifiés ; voir [B52_IMPLEMENTATION.md](docs/architecture/B52_IMPLEMENTATION.md).
- [x] Préparer [la validation Debian 13/Python 3.13](docs/architecture/B52_DEBIAN13_VALIDATION.md) sans modifier la VM existante.
- [x] Validation B5.2 Debian 13 rapportée terminée par l'utilisateur : Python 3.13.5, SQLite 3.46.1, 395 tests, tunnel SSH, simulation/livrable SHA256 et sauvegarde/restauration avec renouvellement des identifiants. Ce résultat ne valide pas l'isolation OS B5.3.
- [ ] Avant un vrai worker : isolation OS éprouvée, politiques réseau/outils/enfants, PKI/appairage/TLS et pile HTTP de production ; conserver le prototype sans IA réelle ni découverte LAN.

**Checkpoint B5.3 — 27 octobre 2026 (worker CPU autonome, OS non vérifié)**

- [x] Vérifier `origin/main` publié à `ef5b293ae91132ff0fda0431318b649184e14348`, créer `feat/webui-control-plane-b53` depuis cette base propre ; commits locaux par lot, aucun push/merge B5.3.
- [x] B5.3a : [contrat versionné](docs/architecture/WORKER_CONTRACT_B53.md), identité cluster distincte UID/GID, capacité CPU fermée, outils vides, déclarations/application/preuves séparées.
- [x] B5.3b/d : nouveau point d'entrée `python3 -m pepeuch_worker`, racine privée et credential local séparés, aucune dépendance au répertoire backend ; SHA256 du texte UTF-8 approuvé, sans shell, fichier d'entrée, fournisseur, GPU ou IA. CLI historique préservée.
- [x] Mission CPU explicite et approbation administrative, intention d'exécution versionnée dans l'audit existant ; migrations 1/2 et contrats historiques conservés, résultats durables/epochs/générations B5.2 réutilisés.
- [x] B5.3e : 443 tests Python réussis (395 historiques inchangés + 48 nouveaux), Firefox B5.1 réussi ; reprise manuelle sans recalcul, pertes de connexion, révocation/rotation, résultats tardifs, sauvegarde/restauration CPU testés.
- [x] B5.3c/f : gabarit systemd/cgroup v2 et [guide Debian 13](docs/architecture/B53_DEBIAN13_VALIDATION.md) préparés ; syntaxe vérifiée seulement, aucune installation/activation/VM modifiée. [Journal B5.3](docs/architecture/B53_IMPLEMENTATION.md).
- [ ] Autoriser puis exécuter les tests négatifs OS sur une machine distincte : UID/groupes, secrets/SQLite/objets inaccessibles, FS, réseau, GPU/Docker, CPU/RAM/PID, runtime et arrêt des enfants — **NOT VERIFIED**.
- [ ] Qualifier le producteur indépendant de permis et fermer/vérifier le réseau OS au port backend ; contrats, observations et canal de refus ajoutés en B5.3.1, sans activation. `--application-test` ne valide pas l'isolation, le filtre IP candidat seul autorise tous les ports loopback.
- [ ] Avant une inférence ou un outil réel : contrat de lecture des versions d'entrée, quotas cumulés I/O/calcul, politique des moteurs/outils, preuves OS et profils Windows/macOS distincts ; conserver AnythingLLM/Open WebUI facultatifs.

**Checkpoint B5.3.1 — 28 octobre 2026 (audit et vérification stricte, OS non qualifié)**

- [x] Vérifier les trois commits B5.3 sur `feat/webui-control-plane-b53`, arbre initial propre ; commits locaux distincts, aucun push/merge ou modification de `main`.
- [x] [Audit de sécurité](docs/architecture/B531_SECURITY_AUDIT.md) : matrice des risques et six reproductions avant correction ; I/O ancrées, verrou sur un seul FD, nettoyage limité à l'inode créé, copie de configuration et rejet des auto-attestations. Régression CLI d'initialisation ajoutée.
- [x] [Contrats de vérification](docs/architecture/ISOLATION_VERIFICATION_B531.md) : exigences/observations/reçus/décisions séparés, contexte PID/starttime/boot/namespaces/cgroup, empreintes et fraîcheur ; aucun succès approximatif sur contrôleur/limite manquant.
- [x] Préparer le canal hérité, vérifier credentials noyau par message, épingler contexte/politique/contrôleur et recontrôler avant claim/calcul/finish/reprise ; la perte de preuve bloque la publication et conserve le journal.
- [x] Préparer [le banc fixe séparé](pilot/worker_isolation/README.md), canaris synthétiques, endpoints privés approuvés et cas de cycle de vie bornés ; aucun préparateur root, contrôleur root ou test négatif OS exécuté.
- [x] Valider **506 tests Python** (443 historiques inchangés + 63 nouveaux), Firefox historique et `git diff --check` ; préserver Control Plane, Discovery Cache et bases POC.
- [ ] Autoriser un pilote négatif sur une **VM jetable distincte** selon [le plan opérateur Debian](docs/architecture/B53_DEBIAN13_VALIDATION.md), avec confirmations séparées pour comptes, fichiers, unités et pare-feu. Aucun accès à la VM historique autorisé.
- [ ] Qualifier collecte indépendante, compte exclusif, code/FD/montages, règles/IPv4/IPv6/ports et ressources/arrêt avant un producteur de permis positif. Le contrôleur livré émet toujours `deny` ; strict reste bloqué, OS **NOT VERIFIED**.
- [ ] Définir si nécessaire une attestation serveur distincte : aucun champ worker ne promeut aujourd'hui le statut `verified`. Pas de vraie inférence, modèle, GPU ou service privilégié permanent.

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
- [x] Comparer les moteurs sur les **mêmes requêtes représentatives**, index et mesures de performance ; aucun choix arrêté.

- [ ] Finaliser le POC comparatif **PostgreSQL vs SurrealDB** (performances, graphe, vecteurs et contraintes d'exploitation).
- [x] Importer un échantillon réel de `models.dev` dans les deux moteurs (ici les 405 TOML du snapshot épinglé).
- [x] Tester les requêtes représentatives :
  - modèle → base model → quantification
  - modèle → provider → coût
  - modèle → runtime → GPU compatible
  - modèle → rôle candidat
  - modèle → benchmark local
- [x] Tester la recherche vectorielle / hybride
- [x] Tester relations de graphe et liens typés
- [x] Tester sauvegarde / restauration sur les deux POC, dans des bases distinctes des sources.
- [x] Tester Docker et consommation mémoire
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

**Checkpoint réel — banc Docker isolé VM150, 28 octobre 2026**

**VERIFIED** : images locales exactes PostgreSQL 16.15 / SurrealDB 3.3.4 ; deux
nouveaux conteneurs non privilégiés, réseau interne sans port publié, 2 CPU / 4 Gio /
256 PID chacun. Paliers 30 → 1 000 → 10 000, huit requêtes avant/après index,
plans obligatoirement validés, latences client et profils d’exécution séparés.
Session Surreal établie avant les mesures ; aucune clé/JWT dans les rapports.

Cinq lignes closes sur ce périmètre **synthétique**, pas sur une charge de production :
comparaison requêtes/index/mesures, requêtes représentatives, vecteur/hybride
**exacts 16 dimensions**, relations typées, Docker/CPU/mémoire. ANN, caches OS
froids, concurrence, qualité d’embeddings et autres parcours restent non validés.
Les snapshots/contrats historiques sont inchangés ; aucune migration/adoption décidée.

Les lots sont découpés entre instructions, bornés à 512 Kio UTF-8 avec transaction
et reçu ; résultat contrôlé avant chaque lot suivant. Interruption entre lots,
reconnexion, reprise et rejeu sans doublon/perte validés dans les deux moteurs.
Huit restaurations vers de nouvelles destinations, empreintes identiques.
Pic cgroup : 157,01 Mio PG / 625,25 Mio Surreal ; aucun OOM/seuil matériel surveillé
sur cette série bornée. Les deux conteneurs d’essai sont arrêtés, artefacts conservés.
POC historiques maintenus arrêtés, métadonnées Docker et montages identiques.

**PARTIAL / BLOCKED** : finalisation du choix DB, revue des contraintes de licence
et validation de la décision. Les mesures favorisent PostgreSQL sur cette charge,
sans classement universel moteur. [Rapport, limites et erreurs conservées](database/poc/ISOLATED_DOCKER_BENCH.md),
[mesures finales avec session](database/poc/results/20261028-vm150-isolated-session/review-manifest.json).

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

**Checkpoint phases 0–3 générales — 28 octobre 2026 (lots locaux)**

**IMPLEMENTED / TESTED** : `manual_discovery_run.py` raccorde les budgets B4.4
aux checkpoints B4.5 sur les sept fixtures. Archives immuables, fraîcheur explicite,
reprise par génération choisie, succès conservés et échecs partiels signalés.
Le plan d’import incrémental reste **non exécutable** : préconditions/rejeu testés
en mémoire, aucune garantie DB réelle revendiquée. CLI et identités historiques
préservées ; aucun transport online, scheduler ou accès aux bases ajouté.
[Contrat et limites](database/poc/MANUAL_INCREMENTAL_RUN.md).

**VERIFIED sur le banc isolé autorisé** : roundtrips B2 des sept sources,
cinq types de ressources, révision simulée sans changement d’identité, champs
inconnus et null/false/zéro/liste vide, scopes incompatibles refusés, non-suppression,
absence de fusion interplateforme, erreurs/reprises et restauration du cache final
à neuf ressources. Tous les snapshots et générateurs historiques sont préservés.
[Preuves réelles](database/poc/ISOLATED_DOCKER_BENCH.md).

**Risque historique reproduit** : les anciens fichiers SQL peuvent remplacer un
état récent. **Correction du SQL régénéré VERIFIED sur synthétique** : transaction
et garde de capture qualifiées dans les deux moteurs ; ancien rejeu et conflit
au même instant refusés sans perte/ajout résiduel, fuseaux équivalents acceptés.

- [x] Protéger les imports B2 nouvellement générés contre les captures anciennes et les conflits au même instant, sans changer clés/empreintes/snapshots ; qualifier sur les bases synthétiques isolées et conserver les anciens artefacts. [Contrat et preuves](database/poc/REPLAY_GUARD_PHASE3.md).

**PARTIAL** : aucune protection rétroactive des anciens SQL, preuve d’ordre des
révisions fournisseur ou isolation comptes/domaines. Le plan CAS reste non
exécutable ; les lots du banc ne constituent pas un Discovery Service automatisé.
Révisions fournisseurs réelles, ordre de publication global, fraîcheur, collecte
et scheduler restent à traiter séparément. Les **35 cases composites ouvertes**
le restent ; cette nouvelle sous-tâche clôturée ne les valide pas entièrement.
Reprise et état Git conservés dans le [nouveau checkpoint durable](docs/audit/CHECKPOINT_20261028_REPRISE_PHASES_0_3.md).

Les révisions distantes, 304 intégrés, émetteurs, domaines/comptes, pagination/SDK,
production HTTP/OS et pilote jetable restent ouverts. [Plan README/About](docs/audit/README_ABOUT_PLAN.md).
Arrêt strict avant 3.1 ; aucun chapitre suivant modifié.

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

## 9.1 Contrat durable des missions sur nœuds temporaires

**Priorité haute — prérequis du lot 10.1.** Décomposer les lignes checkpoints,
retries, pause/reprise et tâches resumable ci-dessus, en réutilisant les primitives
du Control Plane B5 plutôt qu’en créant un second système de missions.

**Principe : le serveur central H24 possède l’état durable des missions.**
Les nœuds temporaires conservent leur environnement d’exécution, leurs modèles
et leur espace de travail ; leurs checkpoints ou résultats en attente de transfert
restent des copies locales non autoritatives, pas une base de missions indépendante.

- [ ] Définir le protocole de drainage : dès notification d’arrêt/redémarrage, refuser localement les nouvelles affectations et notifier le serveur pour qu’il cesse d’en attribuer ; couvrir les affectations déjà en transit.
- [ ] Définir les versions, empreintes, états de tentative et accusés de réception durables des checkpoints/résultats ; confirmer leur persistance centrale avant toute libération des ressources locales correspondantes.
- [ ] Étendre les baux, identifiants idempotents et générations déjà préparés pour refuser les résultats tardifs ou issus d’une ancienne tentative ; prévenir les doubles publications et définir l’idempotence des effets de bord sans promettre une exécution physique unique.
- [ ] Définir la reprise depuis le dernier checkpoint central confirmé ou la réattribution après expiration du bail ; séparer une mission reprenable d’une tâche nécessitant un redémarrage ou une validation humaine.
- [ ] Définir la conduite à tenir si le serveur est indisponible : conserver dans l’espace de travail une file de retransmission bornée et protégée, ne pas annoncer un transfert réussi, puis permettre l’extinction à l’échéance ; documenter la perte possible depuis le dernier checkpoint central confirmé.

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

## 10.1 Cycle de vie des workers temporaires — priorité haute

**Dépendances :** contrat durable 9.1, Runtime Manager phase 7 et qualification
de sécurité/isolation phase 15 et B5.3.1. Le travail de conception et les tests
simulés sont prioritaires ; aucun pilote réel ni service système n’est autorisé
par cette liste. Réutiliser le superviseur et les contrats workers existants.

- [ ] Étudier la détection Linux des demandes d’extinction et de redémarrage via `systemd-logind`, les signaux de préparation et les mécanismes de supervision ; distinguer l’arrêt du worker, celui du nœud et les arrêts non interceptables.
- [ ] Étudier les inhibiteurs d’arrêt en mode délai, `InhibitDelayMaxSec` et les délais des unités systemd ; définir un budget d’arrêt global borné, la libération de l’inhibiteur et la fin du superviseur même en cas de panne réseau, blocage du runtime ou absence du modèle IA.
- [ ] Prévoir un service système indépendant du modèle IA pour piloter détection, drainage et arrêt, avec privilèges minimaux ; documenter son ordre d’arrêt vis-à-vis du réseau, du stockage et du runtime, sans installer de service maintenant.
- [ ] Arrêter immédiatement l’acceptation de nouvelles tâches ; coordonner le drainage avec le serveur selon 9.1 et traiter les courses entre attribution, demande d’arrêt et expiration du bail.
- [ ] Prévoir une terminaison coopérative ou une interruption à une frontière sûre propre à chaque runtime ; borner l’attente et prévoir l’arrêt des processus enfants si le délai expire.
- [ ] Prévoir des checkpoints périodiques et un checkpoint déclenché par arrêt, avec versions d’entrées, progression et intégrité ; mesurer leur coût et leur fréquence sans supposer qu’un état interne de modèle soit toujours sérialisable.
- [ ] Transmettre checkpoints, résultats et livrables au serveur central ; attendre sa confirmation durable avant libération locale, selon 9.1, sans supprimer les seules copies non confirmées.
- [ ] Définir la politique d’expiration du délai : préserver au mieux la file locale de retransmission et autoriser l’extinction sans attendre indéfiniment ; ne pas confondre données locales conservées et résultat durablement acquis par le serveur.
- [ ] Prévoir après redémarrage la reconnexion, le réenregistrement et la réconciliation des baux/tentatives avec le serveur ; reprendre ou retransmettre seulement après décision centrale, sans relancer aveuglément une ancienne affectation.
- [ ] Tester d’abord sur faux workers l’extinction normale, le redémarrage, la coupure brutale, la perte réseau et l’indisponibilité du serveur ; injecter arrêt pendant checkpoint/transfert, accusé perdu et résultat tardif après réattribution.
- [ ] Qualifier ensuite ces scénarios sur des workers de test explicitement autorisés, avec délais mesurés, absence de double publication et reprise depuis les seules versions confirmées ; conserver les preuves et les limites par OS/runtime.

**Critère d’acceptation :** l’extinction de l’ordinateur n’est jamais bloquée
indéfiniment. Un arrêt brutal peut perdre le travail non confirmé ; la mission,
son historique et sa reprise restent sous l’autorité du serveur H24.
Référence de l’étude Linux : [inhibiteurs systemd](https://systemd.io/INHIBITOR_LOCKS/).
Les profils Windows/macOS demanderont une étude distincte ; aucune garantie
Linux n’est transposée automatiquement aux autres systèmes.

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

## 13.1 Étude ECC — agents autonomes et missions longues

Référence à auditer : [affaan-m/ECC](https://github.com/affaan-m/ECC).
**Priorités :** étude comparative après inventaire du Control Plane ; pilote
seulement après les contrats 9.1/10.1 et la qualification de sécurité phase 15.
Cette section planifie une étude, sans adoption, installation ni exécution de hooks.

- [ ] Auditer ECC à un SHA de commit déterminé, en consignant provenance, licence, dépendances et surfaces exécutables ; ne pas traiter sa branche mobile ou ses instructions comme des éléments déjà approuvés.
- [ ] Étudier les skills et agents spécialisés et leur correspondance avec nos rôles, permissions et workflows ; identifier les éléments portables et les dépendances à un outil ou fournisseur.
- [ ] Analyser mémoire persistante, cloisonnement par projet/utilisateur, versionnement, confidentialité et rétention ; distinguer mémoire d’assistance et état durable des missions conservé par le serveur central.
- [ ] Étudier checkpoints, reconstruction de contexte et reprise après interruption ou changement de worker/modèle ; préserver versions d’entrées, provenance et limites de contexte, sans faire de l’historique de conversation la source de vérité.
- [ ] Auditer hooks, chargement de skills, permissions, accès réseau/fichiers et gestion des secrets ; identifier risques d’injection, d’exfiltration et d’élévation de privilèges avant tout essai.
- [ ] Comparer explicitement ECC aux fonctions existantes du Control Plane : missions, approbations, plans/tâches, baux, fichiers versionnés, audit et reprise ; produire une matrice réutilisation/manque/redondance sans dupliquer les primitives B5.
- [ ] Étudier l’exécution autonome de missions longues avec budgets de temps, tokens et coût, limites d’itérations, critères d’arrêt, validations humaines et checkpoints centraux ; conserver un arrêt supervisé indépendant de l’agent.
- [ ] Définir un protocole comparatif avec et sans ECC sur des tâches de référence : qualité, taux de réussite/reprise, durée, CPU/RAM et consommation de tokens/coût ; distinguer compteurs fournisseur et estimations, et conserver les révisions/configurations testées.
- [ ] Préparer puis faire autoriser une expérimentation sur un ou deux workers réels de test, après qualification OS, appairage et réseau ; commencer avec données synthétiques et permissions minimales, sans accès implicite à VM150 ou aux infrastructures privées.
- [ ] Proposer une intégration facultative derrière des contrats/adaptateurs internes, avec solution de remplacement et chemin sans ECC ; rester indépendant de Codex, Claude et des autres fournisseurs de modèles, sans exposer leurs formats propriétaires comme contrat de mission.

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

## 17.1 Intégration continue — GitHub Actions

Décomposition des lignes CI/tests ci-dessus, **sans workflow créé ni activé**.
Livrer progressivement : CI Python et contrôles statiques, intégrations DB
synthétiques, workflows manuels, puis runner GPU après qualification séparée.
**Priorité :** socle Python/contrôles avant les prochains lots d’implémentation ;
intégrations DB après définition de leurs contrats de test ; jobs privilégiés
et GPU seulement après leurs validations et autorisations spécifiques.

- [ ] Prévoir un socle GitHub Actions sous Python **3.13**, exécutant les cinq suites `discovery`, `control_plane`, `infrastructure`, `isolation` et `worker` via `python3.13 tests/run_suites.py -q` ; conserver l’isolation des processus et les règles de tests documentées dans [tests/README.md](tests/README.md).
- [ ] Valider les imports sans chargement implicite de SDK ou accès fournisseur, l’équivalence du point d’entrée Discovery centralisé avec la commande historique, les références B2/B3 et l’absence de modification involontaire des fixtures.
- [ ] Prévoir contrôle Git et espaces (`git diff --check`), propreté de l’arbre après tests, validation de syntaxe/formatage et scan de secrets ; choisir/épingler les outils avant activation, sans reformatage global ni modification des snapshots verbatim pour satisfaire la CI.
- [ ] Documenter les prérequis et limitations des runners publics : contrôles de preuves privées explicitement indisponibles sans exports, pas d’accès VM150/Proxmox/NAS, pas de GPU garanti et aucune qualification négative OS déduite de tests applicatifs ; publier séparément succès, échecs et tests non exécutés, sans faux résultat ni copie des exports privés.
- [ ] Préparer des tests d’intégration PostgreSQL/SurrealDB avec versions/digests épinglés, données synthétiques, bases/volumes/réseaux temporaires et limites de ressources ; vérifier requêtes, relations, anti-rejeu et imports incrémentaux sans dépendance aux POC historiques ni aux fichiers privés des campagnes.
- [ ] Prévoir des workflows **manuels** pour benchmarks et restaurations, avec budgets explicites, destinations nouvelles, contrôle des plans d’exécution et mesures distinctes ; publier uniquement des artefacts revus et non sensibles. Ne pas déclencher les benchmarks lourds à chaque commit ; l’automatisation nocturne éventuelle de phase 8 reste un lot distinct à autoriser.
- [ ] Définir permissions minimales des jobs/tokens, actions épinglées, séparation des contextes fiables/non fiables et protection des secrets dans logs/caches/artefacts ; interdire l’exécution de code de PR non fiable avec secrets ou accès aux infrastructures privées, y compris via un checkout privilégié ou un runner auto-hébergé.
- [ ] Prévoir la validation GPU sur un runner spécialisé seulement après qualification de sécurité : sélection de références de confiance, isolation, quotas, arrêt des processus et autorisation opérateur ; aucune connexion automatique des PR publiques aux machines personnelles ou au LAN.
- [ ] Documenter la matrice des jobs, déclencheurs, dépendances, délais et preuves attendues ; distinguer CI unitaire publique, intégration DB synthétique, benchmark/restauration manuels et qualification matérielle privée.

Référence pour la future conception des permissions :
[sécurité des workflows GitHub Actions](https://docs.github.com/en/actions/reference/security/secure-use).
Les contrôles et études de sécurité phase 15 restent prérequis, pas des validations
acquises par l’ajout de cette liste.

## 17.2 Documentation publique et architecture serveur / workers

Décomposition des lignes documentation et guides ci-dessus ; réutiliser le
[plan README/About existant](docs/audit/README_ABOUT_PLAN.md) et les preuves B5,
sans modifier aujourd’hui README, About ou les statuts des phases 0 à 3.
**Priorité :** clarifier l’état et les prérequis avant toute nouvelle publication
ou ouverture de l’accès aux workers ; compléter les guides à mesure des lots validés.

- [ ] Revoir le README principal pour présenter objectifs, architecture serveur central H24 / workers temporaires et philosophie d’indépendance des fournisseurs d’IA ; distinguer Discovery Cache, Personal Model Catalog, orchestration et runtime.
- [ ] Expliquer l’autorité centrale sur missions, versions, checkpoints et résultats, les seules données d’exécution conservées par les workers, et le cycle d’arrêt/reprise des lots 9.1/10.1, y compris les limites en cas de perte réseau ou coupure brutale.
- [ ] Présenter séparément fonctionnalités opérationnelles, prototypes testés, études et capacités prévues ; dater et lier les preuves, sans présenter GPU visible, catalogue public accessible ou tests applicatifs comme une inférence ou une isolation OS validée.
- [ ] Documenter les prérequis matériels et logiciels : serveur/stockage durable/sauvegardes, CPU/RAM, systèmes supportés, Python/Docker/runtimes et profils GPU/VRAM/pilotes éventuels ; distinguer prérequis minimaux CPU et exigences propres à chaque charge, sans imposer un modèle nommé ou un fournisseur unique.
- [ ] Proposer une description About cohérente avec le README et le statut expérimental, puis faire valider son texte avant toute modification des métadonnées GitHub ; aucune publication implicite.
- [ ] Documenter les cinq suites, leur compatibilité historique et la matrice CI du lot 17.1, les tests privés/GPU/OS non exécutables sur runners publics, ainsi que les procédures manuelles et autorisations requises.
- [ ] Vérifier les liens, les guides serveur/worker et les descriptions des composants tiers ; garder ECC, interfaces tierces et fournisseurs de modèles facultatifs et présenter leurs limites sans promesse de fonctionnalité non livrée.

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
