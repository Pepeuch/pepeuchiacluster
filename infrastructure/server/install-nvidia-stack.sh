#!/usr/bin/env bash
set -euo pipefail

# Pepeuch AI Cluster - NVIDIA stack installer
# Run INSIDE the AI VM after PCIe passthrough is configured and the NVIDIA GPU
# is visible with lspci.
#
# Target: Debian/Ubuntu guest
#
# Installs:
# - NVIDIA driver
# - NVIDIA Container Toolkit
# - Docker runtime configuration
# - validation tests

log()  { printf '[PepeuchAI][NVIDIA] %s\n' "$*"; }
warn() { printf '[PepeuchAI][WARN] %s\n' "$*" >&2; }
fail() { printf '[PepeuchAI][ERROR] %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || fail "Run this script as root."

for cmd in lspci apt-get curl grep awk sed; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing command: $cmd"
done

if ! lspci | grep -Eiq 'NVIDIA|VGA.*NVIDIA|3D controller.*NVIDIA'; then
  fail "No NVIDIA GPU detected in the VM. Check PCIe passthrough before continuing."
fi

log "NVIDIA GPU detected:"
lspci | grep -Ei 'NVIDIA|VGA|3D controller' || true

if [[ ! -r /etc/os-release ]]; then
  fail "/etc/os-release not found."
fi

. /etc/os-release

case "${ID:-}" in
  debian|ubuntu)
    ;;
  *)
    fail "Unsupported distribution: ${ID:-unknown}. Expected Debian or Ubuntu."
    ;;
esac

log "Updating package index..."
apt-get update

log "Installing prerequisites..."
apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  pciutils \
  lsb-release \
  linux-headers-"$(uname -r)" \
  dkms

# ------------------------------------------------------------
# NVIDIA driver
# ------------------------------------------------------------

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  log "NVIDIA driver already installed and working."
else
  if [[ "$ID" == "debian" ]]; then
    log "Installing NVIDIA driver using Debian packages..."

    # Ensure contrib/non-free/non-free-firmware are available on Debian.
    if [[ -f /etc/apt/sources.list ]]; then
      sed -i -E \
        's/^(deb .* main)([[:space:]]*)$/\1 contrib non-free non-free-firmware\2/' \
        /etc/apt/sources.list || true
    fi

    if [[ -d /etc/apt/sources.list.d ]]; then
      for f in /etc/apt/sources.list.d/*.list; do
        [[ -e "$f" ]] || continue
        sed -i -E \
          's/^(deb .* main)([[:space:]]*)$/\1 contrib non-free non-free-firmware\2/' \
          "$f" || true
      done
    fi

    apt-get update
    apt-get install -y nvidia-driver firmware-misc-nonfree

  elif [[ "$ID" == "ubuntu" ]]; then
    log "Installing NVIDIA driver using ubuntu-drivers..."
    apt-get install -y ubuntu-drivers-common
    ubuntu-drivers install
  fi
fi

log "Checking kernel modules..."
if ! lsmod | grep -q '^nvidia'; then
  warn "NVIDIA kernel module is not loaded yet."
  warn "A reboot may be required before nvidia-smi works."
fi

if nvidia-smi >/dev/null 2>&1; then
  log "NVIDIA driver validation successful."
  nvidia-smi
else
  warn "nvidia-smi is not working yet."
  warn "Reboot the VM, then run this script again."
  exit 10
fi

# ------------------------------------------------------------
# NVIDIA Container Toolkit
# ------------------------------------------------------------

if command -v nvidia-ctk >/dev/null 2>&1; then
  log "NVIDIA Container Toolkit already installed."
else
  log "Installing NVIDIA Container Toolkit repository..."

  install -m 0755 -d /usr/share/keyrings

  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

  curl -fsSL \
    https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list

  apt-get update

  log "Installing NVIDIA Container Toolkit..."
  apt-get install -y nvidia-container-toolkit
fi

# ------------------------------------------------------------
# Docker integration
# ------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed. Install Docker before running this script."
fi

log "Configuring NVIDIA runtime for Docker..."
nvidia-ctk runtime configure --runtime=docker

log "Restarting Docker..."
systemctl restart docker

sleep 2

# ------------------------------------------------------------
# Container validation
# ------------------------------------------------------------

log "Testing GPU access from Docker..."

CUDA_TEST_IMAGE="${CUDA_TEST_IMAGE:-nvidia/cuda:12.8.1-base-ubuntu24.04}"

if docker run --rm --gpus all "$CUDA_TEST_IMAGE" nvidia-smi; then
  log "SUCCESS: NVIDIA GPU is accessible from Docker."
else
  fail "Docker GPU test failed."
fi

echo
echo "============================================================"
echo "Pepeuch AI NVIDIA stack is ready."
echo
echo "Host GPU test:"
echo "  nvidia-smi"
echo
echo
echo "Docker GPU test:"
echo "  docker run --rm --gpus all ${CUDA_TEST_IMAGE} nvidia-smi"
echo
echo "Next project step:"
echo "  cd /opt/pepeuch-ai"
echo "  enable the LLM runtime/profile"
echo "============================================================"
