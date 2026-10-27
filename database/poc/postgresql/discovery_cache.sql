-- B2 discovery cache POC. Independent of poc.external_models and personal catalog.
-- Only additive DDL; this does not erase or rewrite existing model records.
CREATE SCHEMA IF NOT EXISTS poc;

CREATE TABLE IF NOT EXISTS poc.discovery_cache (
    record_key          text PRIMARY KEY CHECK (record_key ~ '^d_[0-9a-f]{64}$'),
    source              text NOT NULL,
    entity_type         text NOT NULL CHECK (entity_type IN
                         ('model_reference', 'model_artifact', 'agent_resource',
                          'nim_microservice', 'inference_endpoint')),
    source_id           text NOT NULL,
    source_revision     text,
    display_name        text NOT NULL,
    attributes          jsonb NOT NULL,
    relationships       jsonb NOT NULL CHECK (jsonb_typeof(relationships) = 'array'),
    raw_metadata        jsonb NOT NULL,
    payload_sha256      text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    last_seen_snapshot  text NOT NULL CHECK (last_seen_snapshot ~ '^s_[0-9a-f]{64}$'),
    last_seen_at        timestamptz NOT NULL,
    UNIQUE (source, entity_type, source_id)
);

CREATE INDEX IF NOT EXISTS poc_discovery_source_type_idx
    ON poc.discovery_cache (source, entity_type);

CREATE INDEX IF NOT EXISTS poc_discovery_snapshot_idx
    ON poc.discovery_cache (last_seen_snapshot);
