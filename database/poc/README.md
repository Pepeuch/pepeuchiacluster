# Database POC — models.dev → PostgreSQL

This is an **experiment**, not a final database decision. It uses a disposable
`poc` schema and preserves each model's raw TOML metadata as JSONB.

## Requirements

- Python 3.11+ (standard library only), Git, Docker Compose
- The existing local `infrastructure/docker/compose.db-poc.yaml` PostgreSQL
  service, started as `pepeuch-ai-poc` (not committed yet)
- Initialized pinned `external/models.dev` submodule

Run from the repository root in the AI VM:

```bash
git submodule update --init external/models.dev
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
```

Create the POC schema (does not alter the pre-existing smoke-test table):

```bash
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres psql -X -v ON_ERROR_STOP=1 -U pepeuch_ai -d pepeuch_ai \
  < database/poc/postgresql/schema.sql
```

Perform a transactional, idempotent COPY/upsert of every TOML model:

```bash
set -o pipefail
python3 database/poc/import_models_dev.py | \
  sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
    exec -T postgres psql -X -v ON_ERROR_STOP=1 -U pepeuch_ai -d pepeuch_ai
```

Check the imported snapshot (replace the SHA with the pinned submodule commit):

```bash
sudo docker compose -f infrastructure/docker/compose.db-poc.yaml \
  exec -T postgres psql -X -U pepeuch_ai -d pepeuch_ai \
    -c 'SELECT source_commit, count(*) AS models, count(*) FILTER (WHERE open_weights) AS open_weights FROM poc.external_models GROUP BY source_commit;'
```

There are **no host-published database ports** in this POC. Credentials stay in
`/opt/pepeuch-ai/config/postgres-password`, outside Git.

## Validation boundaries

- Only a restarted container's persistence was previously verified; volume
  re-creation and tested backup/restore are **still pending**.
- This POC tests ingestion, provenance, basic SQL and JSONB. It does **not**
  settle PostgreSQL vs SurrealDB or validate a production relational schema.
- To compare database engines, create identical representative queries and
  record RAM, CPU, execution time and restore behavior on the same sample.
- Never use `docker compose down -v` for this project: it deletes named volumes.
