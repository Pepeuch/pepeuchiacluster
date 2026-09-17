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

- [ ] Réorganiser le repository selon la nouvelle architecture
- [ ] Déplacer les anciens fichiers utiles
- [ ] Archiver les prototypes devenus obsolètes
- [ ] Mettre à jour README et architecture
- [ ] Remplacer l'ancienne TODO par cette TODO v4

---

# Phase 1 — Infrastructure minimale du serveur

- [ ] Créer la VM via le script Proxmox
- [ ] Vérifier réseau / stockage / SSH
- [ ] Passer la RTX A2000 en passthrough
- [ ] Vérifier `lspci`
- [ ] Installer le driver NVIDIA
- [ ] Vérifier `nvidia-smi`
- [ ] Installer NVIDIA Container Toolkit
- [ ] Vérifier le GPU depuis Docker
- [ ] Installer / valider Docker Compose
- [ ] Créer `/opt/pepeuch-ai`
- [ ] Définir volumes persistants
- [ ] Définir sauvegarde de la VM
- [ ] Ajouter healthchecks de base

**Jalon :** un conteneur Docker peut utiliser correctement l'A2000.

---

# Phase 2 — Choix et POC de la base de données

Objectif : choisir le moteur de données avant de figer le schéma.

- [ ] Faire un POC **PostgreSQL vs SurrealDB**
- [ ] Importer un échantillon réel de `models.dev`
- [ ] Tester les requêtes représentatives :
  - modèle → base model → quantification
  - modèle → provider → coût
  - modèle → runtime → GPU compatible
  - modèle → rôle candidat
  - modèle → benchmark local
- [ ] Tester la recherche vectorielle / hybride
- [ ] Tester relations de graphe et liens typés
- [ ] Tester sauvegarde / restauration
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

## 3.1 models.dev — source seed principale

- [ ] Ajouter `anomalyco/models.dev` comme **git submodule**
- [ ] Épingler un commit précis
- [ ] Enregistrer le SHA de source lors des imports
- [ ] Exploiter prioritairement :
  - `models.json`
  - `catalog.json`
  - fichiers TOML `models/`
  - fichiers TOML `providers/`
- [ ] Créer un adapter/importer dédié
- [ ] Ne jamais faire dépendre le selector directement de leur format
- [ ] Détecter les deltas lors des mises à jour du submodule
- [ ] Conserver licence, provider, prix, contexte, modalités, reasoning, tool calling, structured output, open weights et liens vers poids/benchmarks

## 3.2 Hugging Face — enrichissement open-weight

- [ ] Utiliser l'API officielle Hugging Face
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

- [ ] Utiliser le compte NVIDIA Developer
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

**Jalon :** le système peut importer `models.dev`, enrichir un candidat via Hugging Face et NVIDIA, puis produire une fiche normalisée.

# Phase 3.5 — Discovery Cache & Personal Model Catalog

Objectif : ne pas transformer la base locale en miroir géant.

## Discovery Cache

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
