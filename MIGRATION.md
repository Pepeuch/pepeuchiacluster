# Plan de migration du repository

Ce pack prépare la nouvelle organisation du repo autour de :

`External Catalogs → Discovery Cache → Personal Model Catalog → Roles → Selector → Scheduler → Runtime → Workers → Agents → Workflows`

## Mapping conseillé

```text
docs/architecture.md
→ docs/architecture/overview.md

docs/concepts.md
→ docs/concepts/concepts.md

docs/quickstart.md
→ docs/quickstart/quickstart.md

server/bootstrap-ai-server.sh
→ infrastructure/server/bootstrap-ai-server.sh

server/.env.example
→ infrastructure/docker/.env.example

server/compose.yaml
→ archive/prototype-v1/server/compose.yaml

server/scheduler/*
→ archive/prototype-v1/scheduler/*

TODOv1.md / TODOv2.md
→ archive/prototype-v1/

TODO v4
→ TODO.md
```

## Submodule models.dev

Le dossier `external/models.dev/` est volontairement vide dans le ZIP.
Ajoute ensuite le vrai submodule depuis ton clone Git :

```bash
git submodule add https://github.com/anomalyco/models.dev.git external/models.dev
git submodule update --init --recursive
```

## Remarque

Le pack contient les fichiers que nous avons déjà générés dans cette conversation
(TODO, docs, scripts Proxmox/NVIDIA) et la nouvelle structure.
Les fichiers existants de ton repo qui ne sont pas disponibles localement ici doivent
être déplacés selon le mapping ci-dessus.
