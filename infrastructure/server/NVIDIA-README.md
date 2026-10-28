# NVIDIA VM setup

État réel VM150 au 28 octobre 2026 : driver 615.71.10, Secure Boot/MOK,
Toolkit 1.20.1 et GPU visible dans Docker validés par l'utilisateur ; voir le
[checkpoint et ses limites](../../docs/infrastructure/VM150_GPU_20261028.md).
Ne pas réinstaller cette pile pour suivre ce guide. CUDA Docker, inférence et
stabilité prolongée ne sont pas encore validés ; le script d'installation reste
une procédure à examiner pour un nouvel environnement, pas une preuve de ces tests.

Run this script **inside the AI VM** after the NVIDIA GPU has been attached through Proxmox PCIe passthrough.

## Usage

```bash
chmod +x install-nvidia-stack.sh
sudo ./install-nvidia-stack.sh
```

The script verifies that an NVIDIA PCI device is visible before making changes.

It installs and validates:

- NVIDIA driver
- DKMS/kernel prerequisites
- NVIDIA Container Toolkit
- Docker NVIDIA runtime
- GPU access from a CUDA container

## Expected sequence

```text
Proxmox
  ↓
PCIe passthrough
  ↓
AI VM
  ↓
lspci sees NVIDIA GPU
  ↓
install-nvidia-stack.sh
  ↓
nvidia-smi
  ↓
Docker --gpus all
```

If the driver installation requires a reboot, the script exits with code `10`.

Reboot the VM:

```bash
sudo reboot
```

Then run the script again. It is designed to skip already-working components.

## Manual checks

GPU visible on PCI bus:

```bash
lspci | grep -i nvidia
```

Driver:

```bash
nvidia-smi
```

Docker GPU access:

```bash
docker run --rm --gpus all \
  nvidia/cuda:12.8.1-base-ubuntu24.04 \
  nvidia-smi
```

Do not continue with local LLM deployment until the Docker GPU test succeeds.
