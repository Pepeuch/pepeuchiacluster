# Pepeuch AI Cluster

Plateforme IA locale et hybride, pensée pour découvrir, évaluer, sélectionner et exécuter
des modèles et agents sur plusieurs machines hétérogènes.

Architecture directrice :

```text
External Catalogs
      ↓
Discovery Cache
      ↓
Personal Model Catalog
      ↓
Roles / Policies
      ↓
Model Selector
      ↓
Scheduler
      ↓
Runtime Manager
      ↓
Workers
      ↓
Agents / Workflows
```

Voir [`TODO.md`](TODO.md) pour la roadmap et [`MIGRATION.md`](MIGRATION.md) pour le plan de restructuration.

## Prototype local B5.1 — missions et fichiers persistants

Le Control Plane fonctionne sans fournisseur IA, modèle ou GPU. Coordinateur
et worker sont **simulés** ; missions et livrables sont réellement persistants.
Python 3.11–3.13 avec SQLite suffit, sans installation pip.

```bash
export PEPEUCH_B51_DEMO_DIR="$(mktemp -d /tmp/pepeuch-b51-demo.XXXXXX)"
python3 -m control_plane init --data-dir "$PEPEUCH_B51_DEMO_DIR"
printf 'Répertoire de cette démo : %s\n' "$PEPEUCH_B51_DEMO_DIR"
python3 -m control_plane serve --data-dir "$PEPEUCH_B51_DEMO_DIR"
```

Ouvrir `http://127.0.0.1:8765`, copier la clé du fichier privé
`secrets/admin.token` de ce répertoire et créer/approuver une mission.
Dans un second terminal, avec le même `PEPEUCH_B51_DEMO_DIR` :

```bash
python3 -m control_plane worker --data-dir "$PEPEUCH_B51_DEMO_DIR" --once
```

Le serveur écoute uniquement sur loopback. Ce prototype n'est pas destiné à une
exposition LAN/Internet. Le répertoire `/tmp` sert ici à une démo jetable ; choisir
un répertoire durable privé hors du code pour conserver les missions au-delà du
nettoyage de `/tmp`. Guide complet, tests, limites et sauvegarde :
[B51_IMPLEMENTATION.md](docs/architecture/B51_IMPLEMENTATION.md).
