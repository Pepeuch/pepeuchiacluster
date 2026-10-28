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

État au 28 octobre 2026 : [audit des phases 0–3 et validations restantes](docs/audit/PHASES_0_3_COVERAGE.md).
La VM150 dispose du GPU ; ses deux POC de bases sont actuellement arrêtés et
préservés. Le Discovery manuel est testé sur fixtures, le mode worker strict
refuse tant que l’isolation OS n’est pas qualifiée. Aucune inférence ou collecte
planifiée de production n’est annoncée. [Architecture et limites actuelles](docs/architecture/overview.md).
Un [banc Docker isolé sur VM150](database/poc/ISOLATED_DOCKER_BENCH.md) valide
PostgreSQL/SurrealDB sur 30 à 10 000 modèles synthétiques, avec plans, reprise
entre lots et restaurations. Les conteneurs d’essai sont arrêtés et conservés ;
cela n’active ni les POC historiques ni un Discovery Service de production.

Suites automatisées : `python3 tests/run_suites.py -q` ;
[organisation, commandes et preuves privées facultatives](tests/README.md).

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

## B5.2 — sécurité et résilience locales

HTTP borné, sauvegardes/restaurations vérifiées hors ligne et registre de workers
avec révocation et rotation des credentials. L'exécution reste simulée, sur
loopback uniquement ; aucune isolation OS ou exposition production n'est annoncée.

Les commandes `backup`, `restore`, `worker-enroll` et `worker-rotate` sont
documentées dans [B52_IMPLEMENTATION.md](docs/architecture/B52_IMPLEMENTATION.md).
Une restauration crée de nouvelles clés et conserve les workers révoqués jusqu'à
leur réactivation explicite. La procédure de
[validation Debian 13/Python 3.13](docs/architecture/B52_DEBIAN13_VALIDATION.md)
est documentée ; l'utilisateur a depuis confirmé sa réussite sur Debian 13
(395 tests, livrable vérifié et sauvegarde/restauration). La mission B5.3 n'a
effectué aucune nouvelle intervention sur cette VM.

## B5.3 — worker CPU autonome, validation OS à poursuivre

Le nouveau point d'entrée `python3 -m pepeuch_worker` utilise son propre répertoire
privé et un credential worker livré séparément. Une mission CPU explicitement
approuvée calcule SHA256 du texte UTF-8 de l'objectif, sans IA, GPU, shell ou accès
aux fichiers backend. La démonstration B5.1/B5.2 garde son point d'entrée.

Le parcours fonctionne en test applicatif explicite. **Le mode strict refuse
actuellement l'exécution : l'isolation OS est NOT VERIFIED.** Les gabarits systemd
ne sont pas installés ni activés. Contrats, 443 tests Python et limites dans le
[journal B5.3](docs/architecture/B53_IMPLEMENTATION.md) ; procédure proposée pour
une machine distincte autorisée dans le [guide Debian 13](docs/architecture/B53_DEBIAN13_VALIDATION.md).
