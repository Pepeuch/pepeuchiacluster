-- Disposable PostgreSQL POC schema. Not the production catalog schema.
-- Keep imports for different pinned models.dev commits side by side.
CREATE SCHEMA IF NOT EXISTS poc;

CREATE TABLE IF NOT EXISTS poc.external_models (
    source             text NOT NULL,
    source_commit      text NOT NULL CHECK (source_commit ~ '^[0-9a-f]{40}$'),
    source_path        text NOT NULL,
    model_id           text NOT NULL,
    display_name       text NOT NULL,
    family             text,
    open_weights       boolean,
    context_tokens     bigint,
    tools_supported    boolean,
    weights_count      integer NOT NULL CHECK (weights_count >= 0),
    benchmarks_count   integer NOT NULL CHECK (benchmarks_count >= 0),
    raw_metadata       jsonb NOT NULL,
    imported_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, source_commit, source_path)
);

CREATE INDEX IF NOT EXISTS poc_external_models_model_id_idx
    ON poc.external_models (model_id);

CREATE INDEX IF NOT EXISTS poc_external_models_capabilities_idx
    ON poc.external_models (source_commit, family, open_weights);

CREATE INDEX IF NOT EXISTS poc_external_models_raw_metadata_idx
    ON poc.external_models USING gin (raw_metadata);
