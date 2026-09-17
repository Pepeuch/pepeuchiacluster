# Server stack — Pepeuch AI Cluster

This directory contains the **central server stack** for the AI VM.

## Important architecture correction: Orca

Orca is currently distributed as a **desktop application** for Linux, Windows and macOS, not as a headless server container.

For that reason, this stack does **not** attempt to run Orca inside Docker.

The intended architecture is:

```text
M6800 / workstation
└── Orca desktop
      │
      │ SSH / Git / remote agents
      ▼
AI server
├── Ray Head
├── Scheduler
├── PostgreSQL
├── Open WebUI
├── model runtimes
└── workers
```

This keeps Orca as the agent-development/control interface while the server remains the persistent compute and scheduling layer.

## Core services

The bootstrap starts only:

- PostgreSQL
- Ray Head
- Open WebUI

Optional profiles are included but intentionally disabled:

- `llm` → Ollama
- `rag` → Qdrant
- `scheduler` → scheduler skeleton

This follows the project rule: **do not enable a layer before the previous one is validated**.

## Bootstrap

From inside the AI VM:

```bash
cd server
sudo ./bootstrap-ai-server.sh
```

The script:

1. creates persistent directories under `/opt/pepeuch-ai`;
2. copies `.env.example` to `.env`;
3. generates database and WebUI secrets;
4. validates the Compose file;
5. starts PostgreSQL, Ray Head and Open WebUI.

## URLs

After startup:

```text
Open WebUI     http://AI_VM_IP:3000
Ray dashboard  http://AI_VM_IP:8265
```

## Optional profiles

### Local model runtime

Only after GPU passthrough, NVIDIA driver and NVIDIA Container Toolkit are validated:

```bash
docker compose --profile llm up -d
```

### Qdrant / RAG

Only when document indexing/RAG is introduced:

```bash
docker compose --profile rag up -d
```

### Scheduler skeleton

Only when job management development begins:

```bash
docker compose --profile scheduler up -d
```

The initial scheduler only exposes health/status endpoints. Real priority, preemption, resource profiles and job persistence belong to later TODO phases.

## Why Ray uses host networking

The Ray Head container uses Linux host networking so external physical workers can reach it using the AI VM's LAN address instead of a private Docker bridge address.

Expected future worker connection:

```text
ray start --address=<AI_VM_IP>:6379
```

## Model runtime isolation

A future model does not have to use Ollama.

Specialized agents may use dedicated containers with:

- llama.cpp
- PyTorch
- Transformers
- TensorRT-LLM
- vLLM
- ONNX Runtime

The scheduler should select a **role**, while the model registry selects the concrete model/runtime.

## Security

The current stack is intended for a trusted LAN during development.

Before exposing any service outside the LAN:

- configure authentication;
- restrict firewall rules;
- use TLS/reverse proxy;
- never expose Ray directly to the Internet;
- keep `.env` out of Git.
