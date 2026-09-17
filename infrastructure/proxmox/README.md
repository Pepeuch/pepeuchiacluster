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
