# Quickstart — Pepeuch AI Cluster

> Ce quickstart décrit la mise en route **minimale** du projet.
>
> L'objectif n'est pas de déployer tout le cluster immédiatement, mais de valider d'abord le MVP :
>
> **M6800 → Web UI → VM IA Proxmox → RTX A2000 → modèle local → premier agent READ-ONLY**

---

## 1. Prérequis

### Serveur principal

- Proxmox VE
- Une VM Linux dédiée à l'IA
- NVIDIA RTX A2000 12 Go passée à la VM
- Accès réseau au stockage central
- Docker
- NVIDIA Container Toolkit

### Client

N'importe quelle machine du réseau local avec :

- navigateur Web
- SSH
- Git

Le M6800 peut parfaitement servir de poste de pilotage.

### Workers secondaires

Ils ne sont **pas nécessaires au premier démarrage**.

Ils seront ajoutés plus tard :

- station de travail — RTX 5060 Ti 16 Go
- NUC9 — RTX 4060 8 Go

---

# 2. Cloner le dépôt

Dans la VM IA :

```bash
git clone https://github.com/<USER>/pepeuchiacluster.git
cd pepeuchiacluster
```

Remplacer `<USER>` par le propriétaire réel du dépôt GitHub.

---

# 3. Préparer la VM IA

Une Debian ou Ubuntu Server récente est recommandée.

Mettre à jour le système :

```bash
sudo apt update
sudo apt upgrade -y
```

Installer les outils de base :

```bash
sudo apt install -y   git   curl   wget   ca-certificates   gnupg   htop   nvme-cli   pciutils   jq
```

---

# 4. Vérifier le GPU NVIDIA

Après installation du driver NVIDIA :

```bash
nvidia-smi
```

La RTX A2000 doit apparaître correctement.

Exemple attendu :

```text
NVIDIA RTX A2000
Memory-Usage: ...
Driver Version: ...
CUDA Version: ...
```

Ne pas continuer tant que `nvidia-smi` ne fonctionne pas correctement.

---

# 5. Installer Docker

Suivre de préférence la documentation officielle Docker pour la distribution utilisée.

Une fois Docker installé :

```bash
docker --version
```

Puis tester :

```bash
sudo docker run --rm hello-world
```

---

# 6. Installer NVIDIA Container Toolkit

Installer NVIDIA Container Toolkit sur la VM IA.

Après configuration du runtime Docker, tester l'accès GPU depuis un conteneur :

```bash
docker run --rm --gpus all   nvidia/cuda:12.8.0-base-ubuntu24.04   nvidia-smi
```

La RTX A2000 doit apparaître depuis le conteneur.

**Jalon obligatoire :**

```text
Host Linux
   ↓
Docker
   ↓
NVIDIA Container Toolkit
   ↓
RTX A2000 visible dans le conteneur
```

---

# 7. Démarrer un premier runtime LLM

Pour le MVP, commencer avec **un seul runtime**.

Deux choix recommandés :

- Ollama
- llama.cpp

Le but initial est simplement de vérifier qu'un modèle local peut :

- se charger ;
- utiliser le GPU ;
- répondre ;
- libérer ses ressources correctement.

Ne pas ajouter Ray, Orca ou plusieurs modèles à ce stade.

---

# 8. Tester un premier modèle léger

Commencer par un modèle de petite taille, typiquement :

```text
4B à 8B
```

Objectifs :

- mesurer la VRAM utilisée ;
- mesurer les tokens/s ;
- vérifier la stabilité ;
- tester le chargement/déchargement ;
- vérifier l'accès depuis une autre machine du réseau.

Noter les résultats dans :

```text
docs/benchmarks/
```

Exemple :

```text
GPU: RTX A2000 12 Go
Model: ...
Quantization: ...
VRAM: ...
RAM: ...
Tokens/s: ...
Context: ...
```

---

# 9. Ajouter l'interface Web

Installer une interface compatible avec le runtime choisi.

Exemple :

```text
Open WebUI
```

Le flux minimal devient alors :

```text
M6800
  ↓
Navigateur
  ↓
Open WebUI
  ↓
Runtime local
  ↓
RTX A2000
```

À ce stade, le système doit déjà être utilisable depuis n'importe quel poste du réseau local.

---

# 10. Ajouter le premier agent READ-ONLY

Le premier agent recommandé est l'agent fichiers.

Il doit uniquement pouvoir :

- lire ;
- scanner ;
- hasher ;
- récupérer les métadonnées ;
- classifier ;
- produire un rapport.

Il ne doit **pas** :

- supprimer ;
- déplacer ;
- renommer ;
- modifier.

Exemple de workflow :

```text
répertoire
   ↓
scan
   ↓
hash
   ↓
MIME / extension
   ↓
métadonnées
   ↓
classification
   ↓
rapport
```

Le premier objectif est la sécurité et la reproductibilité.

---

# 11. Ajouter le système de jobs

Une fois le premier agent stable :

```text
queued
  ↓
running
  ↓
completed / failed
```

Ajouter progressivement :

- logs ;
- retry ;
- timeout ;
- résultat ;
- priorité ;
- batch.

À ce stade, tout peut encore tourner uniquement sur le serveur.

---

# 12. Ajouter le scheduler

Le scheduler est ajouté **avant les workers externes**.

Politique de départ recommandée :

```text
100  interaction utilisateur
 80  incident infrastructure
 50  audit demandé
 20  classification
 10  indexation nocturne
  5  maintenance opportuniste
```

Tester :

- tâche nocturne ;
- pause ;
- reprise ;
- préemption ;
- chargement/déchargement de modèle.

---

# 13. Ajouter Ray

Ray n'est ajouté qu'après validation du MVP local.

Architecture :

```text
Serveur
  └── Ray Head

A2000
  └── Worker H24

Station
  └── Worker Heavy

NUC9
  └── Worker Light
```

Objectif du premier test :

```text
le serveur envoie un job
        ↓
la station l'exécute
        ↓
le résultat revient au serveur
```

Ne pas commencer par un gros modèle.

Tester d'abord :

- job CPU ;
- job GPU simple ;
- contrainte de ressource ;
- worker indisponible ;
- reprise normale.

---

# 14. Ajouter la station de travail

Profil recommandé :

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

La station peut démarrer depuis un SSD USB 3 dédié contenant :

- Linux minimal ;
- Docker ;
- NVIDIA Container Toolkit ;
- Ray worker ;
- NFS client ;
- SSH ;
- service auto-join.

---

# 15. Ajouter le NUC9

Profil recommandé :

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

Le NUC doit utiliser la même image système que la station autant que possible.

Seul le profil matériel doit changer.

---

# 16. Ajouter Orca

Orca intervient **après** le fonctionnement correct du cluster Ray.

Rôles :

```text
Orca   = quel agent doit travailler ?
Ray    = sur quelle machine ?
Docker = dans quel environnement ?
Runtime IA = comment exécuter le modèle ?
```

Exemple :

```text
Demande utilisateur
        ↓
Orca
        ↓
Agent PCB
        ↓
Scheduler
        ↓
Ray
        ↓
5060 Ti
        ↓
conteneur spécialisé
        ↓
résultat
```

---

# 17. Ajouter progressivement les workflows

Ne pas tout intégrer en même temps.

Ordre recommandé :

1. fichiers ;
2. documentation ;
3. repos Git ;
4. Proxmox READ-ONLY ;
5. photos ;
6. vidéos ;
7. ROMs ;
8. PCB ;
9. Home Assistant / Frigate / Hailo.

---

# 18. Règles de sécurité

Toujours respecter cette hiérarchie :

```text
READ          = automatique
ANALYZE       = automatique
PROPOSE       = automatique
WRITE         = selon politique
DESTRUCTIVE   = confirmation humaine obligatoire
```

Par défaut :

- stockage monté en lecture seule ;
- pas de root direct ;
- pas de suppression automatique ;
- logs de toutes les actions ;
- secrets hors Git ;
- permissions minimales.

---

# 19. Structure recommandée

```text
pepeuchiacluster/
├── README.md
├── TODO.md
├── LICENSE
├── docs/
│   ├── architecture.md
│   ├── quickstart.md
│   └── benchmarks/
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

---

# 20. MVP validé

Le MVP est considéré comme validé lorsque :

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

fonctionne de manière stable, documentée et reproductible.

**Ne pas ajouter les workers externes avant ce jalon.**

---

# Étape suivante

Une fois le MVP validé :

```text
5060 Ti
   ↓
premier worker externe
   ↓
Ray
   ↓
premier job distribué
```

Puis seulement :

```text
NUC9
   ↓
Orca
   ↓
workflows spécialisés
```

---

## Philosophie du projet

> Commencer simple.  
> Valider chaque brique.  
> Documenter.  
> Mesurer.  
> Automatiser ensuite.  
> Ne jamais ajouter une couche tant que la précédente n'est pas stable.