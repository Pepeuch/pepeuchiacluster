# TODO — Local AI Cluster

> Objectif : construire une plateforme IA locale, modulaire et reproductible, pilotée depuis une seule interface, capable d'exécuter des agents permanents sur le serveur Proxmox, de planifier des tâches de fond et de mobiliser ponctuellement des workers GPU plus puissants.

## Principes d'architecture

- **Serveur Proxmox = cerveau H24**
  - Orchestrateur central
  - Scheduler
  - Base de données
  - Stockage central
  - RTX A2000 12 Go
  - Agents et modèles permanents/légers
- **Station de travail = worker lourd à la demande**
  - RTX 5060 Ti 16 Go
  - Gros modèles / vision / tâches lourdes
- **NUC9 = worker léger**
  - RTX 4060 8 Go
  - Classification, embeddings, petits modèles, jobs parallèles
- **M6800 = poste de pilotage**
  - Interface Web
  - SSH / Git
  - Aucun besoin de modèle local
- **Workers temporaires**
  - SSD USB 3 dédié
  - Linux minimal
  - Docker
  - NVIDIA Container Toolkit
  - Ray worker
  - NFS client
- **Séparation des responsabilités**
  - Orca : choix / orchestration des agents
  - Ray : placement des jobs sur les ressources disponibles
  - Docker : isolation des runtimes et dépendances
  - Ollama / llama.cpp / vLLM / TensorRT / PyTorch : exécution des modèles

---

# Phase 0 — Initialiser le projet

- [x] Créer le dépôt GitHub
- [x] Choisir une licence
- [x] Créer le README principal
- [x] Définir le nom du projet
- [x] Ajouter le schéma global d'architecture
- [x] Créer l'arborescence initiale :

```text
project/
├── README.md
├── TODO.md
├── LICENSE
├── docs/
├── server/
├── workers/
├── agents/
├── models/
├── workflows/
├── scheduler/
├── security/
├── scripts/
└── ansible/
```

- [x] Définir les concepts :
  - node
  - worker
  - model
  - agent
  - role
  - workflow
  - job
  - resource profile
- [x] Décider qu'un workflow dépend de **rôles**, pas de modèles nommés en dur

---

# Phase 1 — VM IA minimale sur Proxmox

- [ ] Créer une VM Debian/Ubuntu dédiée
- [ ] Allouer CPU/RAM raisonnablement
- [ ] Passer la RTX A2000 12 Go à la VM
- [ ] Installer le driver NVIDIA
- [ ] Installer Docker
- [ ] Installer NVIDIA Container Toolkit
- [ ] Vérifier l'accès GPU depuis Docker
- [ ] Vérifier CUDA
- [ ] Mesurer :
  - VRAM disponible
  - RAM
  - température
  - consommation
- [ ] Documenter l'installation

**Jalon :** un conteneur Docker peut utiliser l'A2000 correctement.

---

# Phase 2 — Premier modèle local

- [ ] Installer Ollama ou llama.cpp
- [ ] Charger un petit modèle 4B–8B
- [ ] Tester :
  - chargement
  - déchargement
  - génération
  - contexte
  - tokens/s
- [ ] Mesurer la VRAM consommée
- [ ] Tester l'accès distant depuis le M6800
- [ ] Ajouter une interface Web simple

**Jalon :** dialogue local depuis n'importe quel poste de la maison.

---

# Phase 3 — Services centraux

- [ ] Ajouter Open WebUI ou interface équivalente
- [ ] Ajouter PostgreSQL
- [ ] Définir les tables :
  - nodes
  - models
  - jobs
  - agents
  - workflows
  - events
- [ ] Ajouter Qdrant uniquement lorsque le RAG devient nécessaire
- [ ] Définir le stockage des logs
- [ ] Créer une API interne minimale
- [ ] Ajouter healthchecks

---

# Phase 4 — Registre des modèles

- [ ] Créer `models/registry.yaml`
- [ ] Pour chaque modèle stocker :
  - nom
  - source
  - licence
  - type
  - runtime
  - taille
  - quantification
  - VRAM minimale
  - RAM minimale
  - rôles
  - modèles de GPU compatibles
  - persistent / on-demand
  - temps de chargement
- [ ] Définir des profils :
  - 8 Go
  - 12 Go
  - 16 Go
- [ ] Ajouter les premiers rôles :
  - general
  - code
  - embedding
  - rerank
  - OCR
  - vision
  - filesystem
  - infra
  - pcb-schematic
  - pcb-placement
  - pcb-routing
  - pcb-review

---

# Phase 5 — Premier agent utile : fichiers

- [ ] Créer un agent **READ-ONLY**
- [ ] Scanner un répertoire test
- [ ] Récupérer :
  - chemin
  - taille
  - dates
  - MIME
  - hash
  - extension
  - métadonnées
- [ ] Détecter les doublons exacts
- [ ] Classifier les fichiers
- [ ] Produire un rapport
- [ ] Interdire toute suppression automatique
- [ ] Interdire tout déplacement automatique au début
- [ ] Journaliser toutes les décisions

**Jalon :** audit utile sans aucun risque sur les données.

---

# Phase 6 — Système de jobs

- [ ] Créer une structure de job
- [ ] États :
  - queued
  - running
  - paused
  - completed
  - failed
  - cancelled
- [ ] Ajouter :
  - retry
  - timeout
  - dépendances
  - logs
  - métriques
  - résultat
- [ ] Ajouter support de jobs batch
- [ ] Préparer les jobs resumable/checkpointables

---

# Phase 7 — Scheduler

- [ ] Gérer les priorités
- [ ] Gérer les fenêtres horaires
- [ ] Gérer les tâches interactives
- [ ] Gérer les tâches nocturnes
- [ ] Gérer les tâches préemptibles
- [ ] Gérer les tâches non préemptibles
- [ ] Définir une politique initiale :

```text
100  interaction utilisateur
 80  incident / alerte infrastructure
 50  audit explicitement demandé
 20  classification
 10  indexation nocturne
  5  maintenance opportuniste
```

- [ ] Ajouter un système de pause/reprise
- [ ] Ajouter un système de déchargement des modèles faibles priorités
- [ ] Ajouter une politique d'éviction VRAM
- [ ] Ajouter un cache/LRU des modèles

**Jalon :** une demande interactive peut interrompre proprement une tâche de fond.

---

# Phase 8 — Tâches planifiées

- [ ] Indexation nocturne
- [ ] Audit fichiers
- [ ] Génération d'embeddings
- [ ] Classification documents
- [ ] Audit repos Git
- [ ] Maintenance DB
- [ ] Rapports matinaux
- [ ] Vérifier qu'une tâche nocturne peut être arrêtée/reprise

---

# Phase 9 — Agent Proxmox READ-ONLY

- [ ] Lire l'état des VM/LXC
- [ ] Lire CPU/RAM
- [ ] Lire stockage
- [ ] Lire SMART
- [ ] Lire ZFS si utilisé
- [ ] Lire les sauvegardes
- [ ] Lire les erreurs système
- [ ] Lire les journaux
- [ ] Produire des diagnostics
- [ ] Produire des recommandations
- [ ] Aucun accès root direct
- [ ] Aucune modification automatique

---

# Phase 10 — Modèle de sécurité

- [ ] Formaliser les niveaux d'autorisation :

```text
READ          = automatique
ANALYZE       = automatique
PROPOSE       = automatique
WRITE         = selon politique
DESTRUCTIVE   = confirmation humaine obligatoire
```

- [ ] Créer des comptes système dédiés
- [ ] Utiliser sudoers minimal
- [ ] Monter les datasets en lecture seule par défaut
- [ ] Journaliser toutes les actions
- [ ] Ajouter audit trail
- [ ] Ajouter secrets hors Git
- [ ] Ajouter `.env.example`
- [ ] Documenter le modèle de menace

---

# Phase 11 — Premier SSD AI Worker

## Station de travail — RTX 5060 Ti 16 Go

- [ ] Préparer SSD USB 3
- [ ] Debian minimal
- [ ] Driver NVIDIA
- [ ] Docker
- [ ] NVIDIA Container Toolkit
- [ ] Ray worker
- [ ] NFS client
- [ ] SSH
- [ ] service systemd auto-join
- [ ] Monter les modèles locaux nécessaires
- [ ] Monter les données serveur en lecture seule
- [ ] Créer profil :

```yaml
role: heavy
vram_gb: 16
capabilities:
  - cuda
  - heavy-llm
  - vision
  - large-context
  - pcb-heavy
```

---

# Phase 12 — Ray distribué

- [ ] Installer Ray Head sur le serveur
- [ ] Enregistrer l'A2000 comme worker permanent
- [ ] Joindre la station 5060 Ti
- [ ] Déclarer les custom resources
- [ ] Tester un job CPU
- [ ] Tester un job GPU
- [ ] Tester un job avec contrainte `VRAM16`
- [ ] Tester un job qui attend lorsque la ressource n'est pas disponible

**Jalon :** le serveur déclenche un calcul exécuté réellement sur la station.

---

# Phase 13 — Premier gros modèle déporté

- [ ] Choisir un modèle 14B–24B quantifié adapté à la 5060 Ti
- [ ] Créer son conteneur dédié
- [ ] Déclarer son runtime
- [ ] Lancer le modèle depuis un job central
- [ ] Retourner le résultat au serveur
- [ ] Libérer la VRAM après usage
- [ ] Mesurer :
  - temps de chargement
  - tokens/s
  - VRAM
  - consommation

---

# Phase 14 — Worker NUC9 / RTX 4060 8 Go

- [ ] Cloner l'image du SSD worker
- [ ] Adapter uniquement le profil
- [ ] Déclarer :

```yaml
role: light
vram_gb: 8
capabilities:
  - cuda
  - small-llm
  - embedding
  - classification
  - light-vision
```

- [ ] Joindre au cluster
- [ ] Tester 3 nœuds simultanément
- [ ] Tester la répartition automatique

---

# Phase 15 — Scheduling intelligent multi-node

- [ ] A2000 prioritaire pour services H24
- [ ] 4060 pour petites tâches parallèles
- [ ] 5060 Ti pour grosses tâches
- [ ] Fallback entre workers compatibles
- [ ] File d'attente si aucun worker adapté
- [ ] Affinité par GPU
- [ ] Affinité par runtime
- [ ] Limites thermiques éventuelles
- [ ] Limites horaires
- [ ] Préemption
- [ ] Reprise de jobs
- [ ] Dashboard d'état du cluster

---

# Phase 16 — Orca / orchestration d'agents

- [ ] Installer Orca
- [ ] Tester un agent code simple
- [ ] Tester worktree Git isolé
- [ ] Définir la séparation :
  - Orca = **qui**
  - Ray = **où**
  - Docker = **avec quelles dépendances**
- [ ] Connecter les agents au scheduler
- [ ] Ne pas donner de droits administratifs larges aux agents
- [ ] Ajouter validation humaine sur actions sensibles

---

# Phase 17 — Workflows réels

- [ ] `photo-audit`
- [ ] `video-audit`
- [ ] `rom-sort`
- [ ] `document-index`
- [ ] `repo-audit`
- [ ] `proxmox-health`
- [ ] `pcb-design`

## Exemple PCB

```text
datasheets
   ↓
schematic model
   ↓
ERC
   ↓
placement model
   ↓
routing model
   ↓
DRC
   ↓
review model
```

- [ ] Les workflows demandent des rôles, pas des modèles fixes
- [ ] Le registre choisit le meilleur modèle disponible

---

# Phase 18 — Photos / vidéos

- [ ] Hash exact
- [ ] EXIF
- [ ] Détection doublons exacts
- [ ] Détection doublons visuels
- [ ] Embeddings
- [ ] Classification
- [ ] OCR
- [ ] Analyse vidéo par segments lorsque nécessaire
- [ ] Intégration Immich
- [ ] Toujours valider avant suppression
- [ ] Exécuter les écritures finales côté serveur

---

# Phase 19 — ROMs

- [ ] Scan extensions
- [ ] Hash
- [ ] Identification console
- [ ] Intégration DAT No-Intro / Redump si souhaité
- [ ] Normalisation des noms
- [ ] Détection doublons
- [ ] Préparer mouvements par batch
- [ ] Exécuter les mouvements côté serveur
- [ ] Générer rapport avant/après

---

# Phase 20 — Documentation / RAG

- [ ] Extraction texte
- [ ] OCR uniquement si nécessaire
- [ ] Classification
- [ ] Résumé
- [ ] Embeddings
- [ ] Qdrant
- [ ] Reranking
- [ ] Recherche sémantique
- [ ] Indexation de repos / datasheets / docs techniques

---

# Phase 21 — Home Assistant / Frigate / Hailo

- [ ] Frigate propriétaire exclusif du Hailo-8
- [ ] MQTT comme bus d'événements
- [ ] API Frigate
- [ ] Home Assistant API
- [ ] LLM consomme les résultats, pas directement le Hailo
- [ ] Ajouter règles de permission pour actions domotiques
- [ ] Aucun automatisme sensible sans garde-fou

---

# Phase 22 — Reproductibilité

- [ ] Ansible
- [ ] Bootstrap serveur
- [ ] Bootstrap worker
- [ ] Profils GPU génériques
- [ ] Healthchecks
- [ ] Sauvegarde/restauration
- [ ] Documentation d'ajout d'un node
- [ ] Documentation d'ajout d'un modèle
- [ ] Documentation d'ajout d'un agent
- [ ] Documentation d'ajout d'un workflow
- [ ] CI GitHub
- [ ] Tests
- [ ] Versioning des manifests
- [ ] Release stable

---

# MVP à atteindre avant toute complexification

```text
M6800
  ↓
Web UI
  ↓
VM IA Proxmox
  ↓
RTX A2000 12 Go
  ↓
modèle local
  ↓
agent fichiers READ-ONLY
  ↓
scheduler nocturne
```

**Tant que ce MVP n'est pas stable, ne pas ajouter les workers externes.**

---

# Jalon final visé

```text
                           M6800 / Web UI
                                 │
                                 ▼
                         ORCHESTRATEUR CENTRAL
                         Orca + Scheduler + DB
                                 │
                              Ray Head
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       A2000 12 Go H24     5060 Ti 16 Go       4060 8 Go
          Serveur           Heavy Worker        Light Worker
              │                  │                  │
      Agents permanents    Gros modèles       Petits modèles
      RAG / Infra / OCR    Vision / Code       Classification
      Jobs nocturnes       PCB lourd           Embeddings
              └──────────────────┼──────────────────┘
                                 │
                          Stockage central
```

## Règle fondamentale du projet

> **Commencer simple. Valider chaque brique. N'ajouter la suivante que lorsque la précédente est stable, documentée et reproductible.**
