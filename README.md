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
