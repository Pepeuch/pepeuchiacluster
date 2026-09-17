#!/usr/bin/env bash
set -euo pipefail

# Pepeuch AI Cluster - Proxmox VM bootstrap
# Creates a Debian cloud-init VM prepared for the AI stack.
#
# Run this script on the Proxmox host as root.
#
# It intentionally does NOT configure GPU passthrough yet.
# The GPU can be attached later with qm set <VMID> -hostpci0 ...

# -----------------------------
# Defaults
# -----------------------------
VMID="${VMID:-9200}"
VMNAME="${VMNAME:-pepeuch-ai}"
STORAGE="${STORAGE:-local-lvm}"
SNIPPET_STORAGE="${SNIPPET_STORAGE:-local}"
BRIDGE="${BRIDGE:-vmbr0}"

MEMORY_MB="${MEMORY_MB:-24576}"
CORES="${CORES:-8}"
DISK_GB="${DISK_GB:-80}"

CI_USER="${CI_USER:-pepeuch}"
SSH_KEY_FILE="${SSH_KEY_FILE:-/root/.ssh/authorized_keys}"

DEBIAN_RELEASE="${DEBIAN_RELEASE:-13}"
IMAGE_URL="${IMAGE_URL:-https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2}"
IMAGE_FILE="${IMAGE_FILE:-/var/lib/vz/template/iso/debian-${DEBIAN_RELEASE}-genericcloud-amd64.qcow2}"

SNIPPET_DIR="/var/lib/vz/snippets"
USERDATA_NAME="${VMNAME}-user-data.yaml"
USERDATA_PATH="${SNIPPET_DIR}/${USERDATA_NAME}"

# -----------------------------
# Helpers
# -----------------------------
log() {
  echo "[PepeuchAI] $*"
}

fail() {
  echo "[PepeuchAI][ERROR] $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Commande manquante: $1"
}

# -----------------------------
# Checks
# -----------------------------
[[ "$(id -u)" -eq 0 ]] || fail "Ce script doit être exécuté en root sur le host Proxmox."

for cmd in qm pvesm wget awk sed grep; do
  require_cmd "$cmd"
done

if qm status "$VMID" >/dev/null 2>&1; then
  fail "Le VMID ${VMID} existe déjà."
fi

pvesm status | awk '{print $1}' | grep -qx "$STORAGE" || fail "Storage '${STORAGE}' introuvable."
pvesm status | awk '{print $1}' | grep -qx "$SNIPPET_STORAGE" || fail "Snippet storage '${SNIPPET_STORAGE}' introuvable."

mkdir -p "$(dirname "$IMAGE_FILE")"
mkdir -p "$SNIPPET_DIR"

# -----------------------------
# SSH key
# -----------------------------
SSH_KEY=""
if [[ -f "$SSH_KEY_FILE" ]]; then
  SSH_KEY="$(head -n1 "$SSH_KEY_FILE")"
fi

if [[ -z "$SSH_KEY" ]]; then
  log "Aucune clé SSH trouvée dans ${SSH_KEY_FILE}."
  log "La VM sera créée sans clé SSH injectée."
fi

# -----------------------------
# Download cloud image
# -----------------------------
if [[ ! -f "$IMAGE_FILE" ]]; then
  log "Téléchargement de l'image Debian ${DEBIAN_RELEASE}..."
  wget -O "$IMAGE_FILE" "$IMAGE_URL"
else
  log "Image Debian déjà présente: ${IMAGE_FILE}"
fi

# -----------------------------
# Cloud-init user-data
# -----------------------------
log "Création du cloud-init..."

cat > "$USERDATA_PATH" <<EOF
#cloud-config
hostname: ${VMNAME}
manage_etc_hosts: true

users:
  - default
  - name: ${CI_USER}
    groups:
      - sudo
      - docker
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
EOF

if [[ -n "$SSH_KEY" ]]; then
cat >> "$USERDATA_PATH" <<EOF
    ssh_authorized_keys:
      - ${SSH_KEY}
EOF
fi

cat >> "$USERDATA_PATH" <<'EOF'

package_update: true
package_upgrade: true

packages:
  - qemu-guest-agent
  - ca-certificates
  - curl
  - wget
  - git
  - jq
  - htop
  - pciutils
  - usbutils
  - lsb-release
  - gnupg
  - openssh-server
  - python3
  - python3-pip
  - python3-venv
  - nfs-common

write_files:
  - path: /etc/sysctl.d/99-pepeuch-ai.conf
    permissions: '0644'
    content: |
      vm.swappiness=10

  - path: /usr/local/sbin/pepeuch-ai-status
    permissions: '0755'
    content: |
      #!/usr/bin/env bash
      echo "=== Host ==="
      hostnamectl
      echo
      echo "=== CPU / RAM ==="
      lscpu | grep -E 'Model name|Socket|Core|Thread|CPU\(s\)'
      free -h
      echo
      echo "=== PCI ==="
      lspci | grep -Ei 'vga|3d|nvidia|display' || true
      echo
      echo "=== Docker ==="
      docker --version 2>/dev/null || true
      docker info 2>/dev/null | head -n 30 || true

runcmd:
  - systemctl enable --now qemu-guest-agent
  - systemctl enable --now ssh

  # Docker official repository
  - install -m 0755 -d /etc/apt/keyrings
  - curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  - chmod a+r /etc/apt/keyrings/docker.asc
  - |
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  - apt-get update
  - apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

  # Ensure user has Docker access
  - usermod -aG docker ${CI_USER}

  # Prepare project directories
  - mkdir -p /opt/pepeuch-ai/{compose,models,data,logs,cache}
  - chown -R ${CI_USER}:${CI_USER} /opt/pepeuch-ai

  # Create initial compose placeholder
  - |
    cat >/opt/pepeuch-ai/compose/compose.yaml <<'COMPOSE'
    services:
      placeholder:
        image: alpine:latest
        command: ["sh", "-c", "echo 'Pepeuch AI VM ready'; sleep infinity"]
        restart: unless-stopped
    COMPOSE
  - chown -R ${CI_USER}:${CI_USER} /opt/pepeuch-ai/compose

final_message: |
  Pepeuch AI VM bootstrap terminé.
  GPU passthrough et NVIDIA Container Toolkit restent à configurer après installation physique du GPU.
EOF

# -----------------------------
# Create VM
# -----------------------------
log "Création de la VM ${VMID} (${VMNAME})..."

qm create "$VMID" \
  --name "$VMNAME" \
  --ostype l26 \
  --machine q35 \
  --bios ovmf \
  --efidisk0 "${STORAGE}:0,efitype=4m,pre-enrolled-keys=1" \
  --memory "$MEMORY_MB" \
  --cores "$CORES" \
  --cpu host \
  --numa 1 \
  --scsihw virtio-scsi-single \
  --net0 "virtio,bridge=${BRIDGE},firewall=1" \
  --agent enabled=1,fstrim_cloned_disks=1 \
  --serial0 socket \
  --vga serial0 \
  --onboot 1

# -----------------------------
# Import disk
# -----------------------------
log "Import du disque système..."
qm importdisk "$VMID" "$IMAGE_FILE" "$STORAGE"

# Find imported disk volume
IMPORT_VOL="$(pvesm list "$STORAGE" --vmid "$VMID" | awk '/vm-'"$VMID"'-disk-/ {print $1}' | tail -n1)"
[[ -n "$IMPORT_VOL" ]] || fail "Impossible de retrouver le disque importé."

qm set "$VMID" --scsi0 "${IMPORT_VOL},discard=on,ssd=1,iothread=1"
qm resize "$VMID" scsi0 "${DISK_GB}G"

# -----------------------------
# Cloud-init disk
# -----------------------------
qm set "$VMID" --ide2 "${STORAGE}:cloudinit"
qm set "$VMID" --boot order=scsi0
qm set "$VMID" --ipconfig0 ip=dhcp
qm set "$VMID" --ciuser "$CI_USER"

if [[ -n "$SSH_KEY" ]]; then
  TMPKEY="$(mktemp)"
  printf '%s\n' "$SSH_KEY" > "$TMPKEY"
  qm set "$VMID" --sshkeys "$TMPKEY"
  rm -f "$TMPKEY"
fi

# custom user-data snippet
qm set "$VMID" --cicustom "user=${SNIPPET_STORAGE}:snippets/${USERDATA_NAME}"

# -----------------------------
# Optional tuning
# -----------------------------
qm set "$VMID" --balloon 0
qm set "$VMID" --hotplug disk,network,usb,memory,cpu
qm set "$VMID" --startup order=20,up=30,down=60

# -----------------------------
# Done
# -----------------------------
log "VM créée avec succès."
echo
echo "Résumé:"
echo "  VMID         : ${VMID}"
echo "  Nom          : ${VMNAME}"
echo "  CPU          : ${CORES} vCPU"
echo "  RAM          : ${MEMORY_MB} MB"
echo "  Disque       : ${DISK_GB} GB"
echo "  Bridge       : ${BRIDGE}"
echo "  Storage      : ${STORAGE}"
echo
echo "Démarrage:"
echo "  qm start ${VMID}"
echo
echo "Après le premier boot:"
echo "  qm guest cmd ${VMID} network-get-interfaces"
echo
echo "GPU passthrough (plus tard, exemple):"
echo "  qm set ${VMID} -hostpci0 <PCI_DEVICE>,pcie=1"
echo
echo "Le script ne configure volontairement PAS le GPU avant sa présence physique."
