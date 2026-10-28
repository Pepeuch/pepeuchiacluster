# Proxmox AI VM bootstrap

Ce dossier contient le bootstrap Proxmox de la VM centrale de **Pepeuch AI Cluster**.

## Objectif

Créer automatiquement une VM Debian cloud-init préparée pour accueillir :

- Docker ;
- Docker Compose ;
- QEMU Guest Agent ;
- Git ;
- Python ;
- NFS ;
- les futurs services Pepeuch AI Cluster.

Le GPU n'est **pas** attaché automatiquement. Le passthrough NVIDIA sera ajouté lorsque le matériel définitif sera installé.

## Utilisation

Avant toute exécution sur un hyperviseur, plan hors ligne sans root, réseau,
lecture de clé ou commande Proxmox :

```bash
VMID=9500 VMNAME=pepeuch-test-9500 MEMORY_MB=2048 CORES=2 DISK_GB=16 \
  bash infrastructure/proxmox/create-ai-vm.sh --plan
```

L'exécution sans option conserve l'interface historique mais **applique réellement**
le plan : root et GO opérateur nécessaires, VM150 protégée. Aucun essai Proxmox réel
n'est validé par les tests locaux. Python 3 est désormais requis sur l'hôte pour
valider les paramètres avant toute écriture ; aucune installation n'est automatique
sur l'hôte. `SNIPPET_DIR` est surchargeable pour les tests isolés.

`IMAGE_SHA256` permet de vérifier image téléchargée/cache existant. Pour le pilote
réel, fournir le SHA256 vérifié d'une image Debian précise, pas seulement le lien
mobile `latest`. Sans checksum, l'image reste NOT VERIFIED. Aucun fichier cloud-init
préexistant, lien ou image corrompue n'est écrasé. Le disque importé doit être
l'unique `unusedN` attendu, jamais le dernier volume trouvé au hasard.

Le compte cloud-init est un **administrateur de VM** (sudo sans mot de passe et
groupe docker), pas un worker isolé. La clé doit être une ligne publique simple,
sans options ; les contenus ne sont pas affichés. Le script ne démarre pas la VM,
n'attache pas de GPU et ne détruit pas automatiquement une création partielle.
Retour arrière : inspecter uniquement les nouveaux VMID/disques/snippets, puis
faire approuver leur retrait ciblé ; jamais agir sur VM150 ou un artefact inconnu.

Copier le script sur le host Proxmox puis :

```bash
chmod +x create-ai-vm.sh
./create-ai-vm.sh
```

## Paramètres

Tous les paramètres principaux sont surchargeables via variables d'environnement.

Exemple :

```bash
VMID=9500 \
VMNAME=pepeuch-ai \
STORAGE=local-lvm \
BRIDGE=vmbr0 \
MEMORY_MB=32768 \
CORES=10 \
DISK_GB=120 \
./create-ai-vm.sh
```

Valeurs par défaut :

```text
VMID=9200
VMNAME=pepeuch-ai
STORAGE=local-lvm
SNIPPET_STORAGE=local
BRIDGE=vmbr0
MEMORY_MB=24576
CORES=8
DISK_GB=80
CI_USER=pepeuch
```

## Ce que le script fait

1. télécharge l'image Debian Generic Cloud ;
2. crée une VM Q35/OVMF ;
3. importe le disque cloud ;
4. ajoute cloud-init ;
5. active QEMU Guest Agent ;
6. installe les outils système ;
7. installe Docker depuis le dépôt officiel ;
8. prépare `/opt/pepeuch-ai/` ;
9. crée un compose placeholder ;
10. laisse le passthrough GPU pour une étape ultérieure.

## GPU

Une fois l'A2000 présente et son IOMMU validé :

```bash
qm set <VMID> -hostpci0 <PCI_DEVICE>,pcie=1
```

Ensuite seulement seront installés dans la VM :

- driver NVIDIA ;
- NVIDIA Container Toolkit ;
- runtime IA ;
- premier modèle local.

## Important

Le script doit être testé sur une VMID non critique avant d'être utilisé sur une installation de production.
