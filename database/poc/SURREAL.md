# SurrealDB POC: same pinned models.dev snapshot as PostgreSQL

This is an **experimental comparison**, not a migration from PostgreSQL.

## Prerequisites

- The `external/models.dev` submodule is checked out at its pinned commit.
- `infrastructure/docker/compose.surreal-poc.yaml` runs SurrealDB v3.3.4,
  with a bind mount from `/opt/pepeuch-ai/data/surreal-poc` to `/data`.
- The image binary is `/surreal` (not `surreal` in `$PATH`).
- Compose supplies `SURREAL_USER` and `SURREAL_PASS` from the local secret
  environment file; **do not pass credentials on the command line**.

These steps run from `/opt/pepeuch-ai/repo` inside VM 150.

## Resource budget (optional but recommended before starting AI agents)

Under the SurrealDB service's `environment:` in the Compose file, keep its
existing settings and add:

```yaml
  SURREAL_ROCKSDB_BLOCK_CACHE_SIZE: "536870912"
  SURREAL_ROCKSDB_WRITE_BUFFER_SIZE: "33554432"
  SURREAL_ROCKSDB_MAX_WRITE_BUFFER_NUMBER: "2"
```

Recreate only the SurrealDB container to apply the settings. The `/data`
bind mount remains untouched:

```bash
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml up -d --wait --force-recreate surrealdb
```

Verify with `sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml logs --tail=80 surrealdb`, and inspect actual memory with
`sudo docker stats --no-stream` (configured cache capacity is not actual RSS).

## Generate a repeatable SurrealQL file

```bash
python3 -m unittest discover -s database/poc -p 'test_*.py' -v
python3 database/poc/import_models_dev_surreal.py > /opt/pepeuch-ai/data/surreal-poc/models-dev-5e9fdbc3.surql
```

Python's diagnostic (including the model count and snapshot SHA) is on stderr.
The `.surql` output begins with `OPTION IMPORT;`, required by the SurrealDB
3.0.4+ import endpoint, and uses deterministic record IDs and `UPSERT ...
CONTENT ... RETURN NONE` for safe retries. Re-importing will not create
duplicate records. Imports apply statement by statement and are not atomic.

## Parse-check locally in the container, then import

```bash
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml exec -T surrealdb \
  /surreal validate /data/models-dev-5e9fdbc3.surql

sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml exec -T surrealdb \
  /surreal import \
  --endpoint http://127.0.0.1:8000 \
  --namespace pepeuch_ai \
  --database poc \
  /data/models-dev-5e9fdbc3.surql
```

The credentials come from `env_file`. **Do not run the import** if validation
fails. Inspect the CLI exit status if the import reports an error; the tool may
have applied a subset before failing. Rerun after fixing the issue.

## Verify parity with the PostgreSQL POC

```bash
printf 'SELECT count() AS total_models FROM external_models GROUP ALL;\n' | \
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml exec -T surrealdb \
  /surreal sql --endpoint http://127.0.0.1:8000 \
  --namespace pepeuch_ai --database poc --hide-welcome

printf 'SELECT count() AS open_weights FROM external_models WHERE open_weights = true GROUP ALL;\n' | \
sudo docker compose -f infrastructure/docker/compose.surreal-poc.yaml exec -T surrealdb \
  /surreal sql --endpoint http://127.0.0.1:8000 \
  --namespace pepeuch_ai --database poc --hide-welcome
```

Expected snapshot totals (without other data loaded in the same SurrealDB
table): 405 models, 196 open weights, 397 positive context, 8 zero context,
154 with weights and 135 with benchmarks. The source is the same pinned
`models.dev` commit used in PostgreSQL; this does not validate model freshness.

Before considering a production store, compare query performance, uptime,
backup/restore, operating costs, permissions, and the actual application data
model. PostgreSQL remains untouched by this POC.
