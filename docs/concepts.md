# Concepts — Pepeuch AI Cluster

Ce document fixe le vocabulaire de base utilisé dans **Pepeuch AI Cluster** afin d'éviter toute ambiguïté entre les notions de machine, worker, modèle, agent, rôle, workflow et job.

## Node

Un **node** est une machine physique ou virtuelle qui participe au cluster et expose des ressources de calcul ou de stockage.

Exemples :

```text
server-a2000
workstation-5060ti
nuc9-4060
```

Un node décrit principalement :

- CPU ;
- RAM ;
- GPU ;
- VRAM ;
- stockage local ;
- runtimes disponibles ;
- disponibilité ;
- capacités particulières.

Un node n'exécute pas directement un workflow : il héberge un ou plusieurs workers.

## Worker

Un **worker** est un processus ou service exécuté sur un node. Il reçoit des jobs du scheduler et les exécute.

Exemples :

```text
worker-llm
worker-vision
worker-embedding
worker-pcb
worker-cpu
```

Un node peut héberger plusieurs workers si ses ressources le permettent.

## Model

Un **model** représente un modèle d'intelligence artificielle concret et versionné.

Il possède notamment :

- un nom ;
- une version ;
- une source ;
- une licence ;
- une taille ;
- une quantification ;
- un runtime ;
- des besoins CPU/RAM/GPU/VRAM ;
- un ou plusieurs rôles qu'il peut remplir ;
- une politique de chargement.

Exemple :

```yaml
name: qwen-kicad-4b
runtime: llama_cpp
min_vram_gb: 4

roles:
  - pcb-kicad
  - pcb-review

persistent: false
```

Un modèle peut être :

```text
stocké sur disque
      ↓
chargé en RAM
      ↓
chargé en VRAM
```

Ces trois états sont distincts.

## Agent

Un **agent** est une logique autonome ou semi-autonome chargée d'accomplir une mission.

Contrairement à un modèle, un agent peut :

- prendre des décisions ;
- utiliser plusieurs modèles ;
- utiliser des outils ;
- appeler des API ;
- consulter des bases de données ;
- déclencher plusieurs jobs ;
- suivre un workflow ;
- produire un résultat final.

Exemples :

```text
filesystem-agent
repo-audit-agent
proxmox-agent
pcb-agent
photo-agent
```

Un agent ne doit pas être lié directement à un modèle précis. Il demande des capacités via des rôles.

## Role

Un **role** représente une capacité abstraite. C'est l'interface entre les workflows/agents et les modèles disponibles.

Exemples :

```text
general
code-review
embedding
rerank
ocr
vision
vision-heavy
filesystem-classification
infra-analysis
pcb-schematic
pcb-placement
pcb-routing
pcb-review
```

Un rôle ne désigne jamais directement un modèle.

Par exemple :

```text
role: pcb-routing
```

peut aujourd'hui être résolu vers :

```text
KiCadRouterAI
```

et demain vers :

```text
SuperRouterV2
```

sans modifier le workflow.

Un même modèle peut remplir plusieurs rôles, et plusieurs modèles peuvent être compatibles avec le même rôle.

# Règle fondamentale : les workflows utilisent des rôles

Un workflow ne doit **jamais dépendre d'un modèle nommé en dur**.

Incorrect :

```yaml
steps:
  - model: SchGen-20B
  - model: KiCadRouterAI
```

Correct :

```yaml
steps:
  - role: pcb-schematic
  - role: pcb-placement
  - role: pcb-routing
  - role: pcb-review
```

Le scheduler et le registre des modèles décident ensuite quel modèle remplit chaque rôle.

Cette séparation permet :

- de remplacer facilement un modèle ;
- de comparer plusieurs modèles ;
- d'ajouter un fallback ;
- de choisir un modèle selon le GPU disponible ;
- de changer de runtime ;
- de faire évoluer le système sans réécrire les workflows.

## Workflow

Un **workflow** décrit une mission complète sous forme d'une suite d'étapes.

Chaque étape demande généralement :

- un rôle ;
- éventuellement des ressources ;
- éventuellement des dépendances ;
- éventuellement des permissions ;
- éventuellement une priorité.

Exemple :

```yaml
workflow: pcb-design

steps:
  - id: schematic
    role: pcb-schematic

  - id: placement
    role: pcb-placement
    depends_on:
      - schematic

  - id: routing
    role: pcb-routing
    depends_on:
      - placement

  - id: review
    role: pcb-review
    depends_on:
      - routing
```

Un workflow est une définition. Il ne représente pas une exécution en cours.

## Job

Un **job** est une instance concrète d'exécution.

Il peut correspondre à :

- une étape de workflow ;
- une tâche indépendante ;
- une mission interactive ;
- une tâche planifiée.

Un job contient notamment :

- un identifiant ;
- un rôle demandé ;
- une priorité ;
- un état ;
- une date de création ;
- des contraintes de ressources ;
- un node/worker assigné ;
- des logs ;
- un résultat ;
- des informations de retry ;
- éventuellement un checkpoint.

États possibles :

```text
queued
running
paused
completed
failed
cancelled
```

Exemple :

```yaml
job:
  id: job-00124
  role: pcb-routing
  priority: 50
  state: queued

  resources:
    min_vram_gb: 6
    gpu_required: true

  preemptible: false
```

## Resource Profile

Un **resource profile** décrit les ressources d'un node, d'un worker ou les besoins d'un job/modèle.

Exemple pour une machine :

```yaml
name: workstation-heavy

cpu_threads: 32
ram_gb: 64

gpu:
  vendor: nvidia
  model: RTX-5060-Ti
  vram_gb: 16

capabilities:
  - cuda
  - heavy-llm
  - vision
  - pcb-heavy

availability:
  persistent: false
```

Exemple de besoin :

```yaml
resources:
  gpu_required: true
  min_vram_gb: 14

  capabilities:
    - cuda
    - heavy-llm
```

Le scheduler fait correspondre :

```text
besoin du job
      ↓
resource profiles disponibles
      ↓
worker compatible
```

# Relations entre les concepts

```text
                         USER
                          │
                          ▼
                        AGENT
                          │
                          ▼
                       WORKFLOW
                          │
                    demande un ROLE
                          │
                          ▼
                   MODEL REGISTRY
                          │
                sélection d'un MODEL
                          │
                          ▼
                         JOB
                          │
                     SCHEDULER
                          │
                          ▼
                       WORKER
                          │
                          ▼
                        NODE
                          │
                          ▼
                    CPU / GPU / RAM
```

# Exemple complet

Demande utilisateur :

```text
Analyse ce PCB et termine le routage.
```

L'agent PCB déclenche :

```text
PCB Agent
   ↓
Workflow pcb-design
   ↓
role: pcb-routing
```

Le registre indique :

```text
KiCadRouterAI
min_vram: 6 Go
runtime: PyTorch
```

Le scheduler recherche une ressource compatible :

```text
A2000 12 Go       → compatible
RTX 4060 8 Go     → compatible
RTX 5060 Ti 16 Go → compatible
```

Selon la disponibilité, la priorité, la charge et la politique du scheduler, le job est envoyé vers un worker.

Exemple :

```text
job pcb-routing
      ↓
Ray
      ↓
worker A2000
      ↓
container KiCadRouterAI
      ↓
résultat
```

Le workflow ne sait jamais quel GPU ou quel modèle concret a été utilisé.

# Principe de découplage

Le projet doit conserver quatre niveaux indépendants :

```text
Workflow
   ↓
Role
   ↓
Model
   ↓
Resource Profile
```

Cela permet de changer :

- le modèle sans changer le workflow ;
- le GPU sans changer l'agent ;
- le runtime sans changer le rôle ;
- le worker sans changer le job.

C'est un principe fondamental de l'architecture de **Pepeuch AI Cluster**.
