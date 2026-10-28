"""Deterministic synthetic workload for the explicitly authorized Docker bench.

No Docker, network, provider API or Personal Model Catalog dependency.
"""

import json
import math


SIZES = (30, 1000, 10000)
TABLES = ("provider", "role", "runtime", "gpu", "model", "variant", "benchmark", "supports", "fits")


def corpus(size):
    if type(size) is not int or size not in SIZES:
        raise ValueError("Only the authorized reduced/1k/10k stages are supported")
    models, variants, benchmarks, supports, fits = [], [], [], [], []
    for i in range(size):
        identity, variant = f"m{i:05d}", f"v{i:05d}"
        embedding = [((i * (d + 3) + d * 7) % 97 + 1) / 97 for d in range(16)]
        models.append({"model_id": identity, "provider_id": f"p{i % 8}",
                       "base_id": None if i % 3 == 0 else f"m{i-i%3:05d}",
                       "name": ("chat-" if i % 2 == 0 else "code-") + identity,
                       "role_id": "assistant" if i % 2 == 0 else "coder", "embedding": embedding})
        variants.append({"variant_id": variant, "model_id": identity, "quant": "q4" if i % 2 == 0 else "f16",
                         "vram_gb": 4 + i % 8 * 2})
        benchmarks.append({"model_id": identity, "score": (i * 7) % 101})
        supports.append({"edge_id": f"s{i:05d}", "variant_id": variant, "runtime_id": f"r{i%2}"})
        for gpu in ("g0", "g1"):
            if variants[-1]["vram_gb"] <= (12 if gpu == "g0" else 24):
                fits.append({"edge_id": f"f{i:05d}{gpu}", "variant_id": variant, "gpu_id": gpu})
    return {"format": "pepeuch-ai.synthetic-engine-workload/v1", "data_kind": "synthetic", "size": size,
            "provider": [{"provider_id": f"p{i}", "input_cost": (i + 1) / 10} for i in range(8)],
            "role": [{"role_id": "assistant", "min_score": 50}, {"role_id": "coder", "min_score": 60}],
            "runtime": [{"runtime_id": "r0", "kind": "cpu"}, {"runtime_id": "r1", "kind": "gpu"}],
            "gpu": [{"gpu_id": "g0", "vram_gb": 12}, {"gpu_id": "g1", "vram_gb": 24}],
            "model": models, "variant": variants, "benchmark": benchmarks, "supports": supports, "fits": fits}


def expected(data):
    models = {r["model_id"]: r for r in data["model"]}
    costs = {r["provider_id"]: r["input_cost"] for r in data["provider"]}
    scores = {r["model_id"]: r["score"] for r in data["benchmark"]}
    gpu = {r["variant_id"] for r in data["fits"] if r["gpu_id"] == "g0"}
    runtime = {r["variant_id"] for r in data["supports"] if r["runtime_id"] == "r1"}
    vector, hybrid = [], []
    for m in models.values():
        score = m["embedding"][0] / math.sqrt(sum(v*v for v in m["embedding"]))
        vector.append({"model_id": m["model_id"], "score": round(score, 8)})
        hybrid.append({"model_id": m["model_id"], "score": round(.75*score + .25*int("chat" in m["name"]), 8)})
    rank = lambda rows: sorted(rows, key=lambda r: (-r["score"], r["model_id"]))[:10]
    return {
        "provider_filter": [{"model_id": m["model_id"]} for m in data["model"] if m["provider_id"] == "p1"][:20],
        "base_quant": [{"model_id": v["model_id"], "base_model": models[v["model_id"]]["base_id"], "quant": v["quant"]}
                       for v in data["variant"] if models[v["model_id"]]["base_id"] is not None][:20],
        "provider_cost": [{"model_id": m["model_id"], "provider_id": m["provider_id"], "input_cost": costs[m["provider_id"]]}
                          for m in data["model"]][:20],
        "runtime_gpu": [{"model_id": v["model_id"]} for v in data["variant"] if v["variant_id"] in gpu & runtime][:20],
        "role_candidate": [{"model_id": m["model_id"]} for m in data["model"]
                           if m["role_id"] == "assistant" and scores[m["model_id"]] >= 50][:20],
        "local_benchmark": [{"model_id": mid, "score": score} for mid, score in
                            sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))[:10]],
        "vector_exact": rank(vector), "hybrid_exact": rank(hybrid),
    }


PG_SCHEMA = """
CREATE TABLE provider(provider_id text PRIMARY KEY,input_cost double precision NOT NULL);
CREATE TABLE role(role_id text PRIMARY KEY,min_score integer NOT NULL);
CREATE TABLE runtime(runtime_id text PRIMARY KEY,kind text NOT NULL);
CREATE TABLE gpu(gpu_id text PRIMARY KEY,vram_gb integer NOT NULL);
CREATE TABLE model(model_id text PRIMARY KEY,provider_id text REFERENCES provider,base_id text REFERENCES model DEFERRABLE INITIALLY DEFERRED,
name text NOT NULL,role_id text REFERENCES role,embedding double precision[] NOT NULL);
CREATE TABLE variant(variant_id text PRIMARY KEY,model_id text REFERENCES model,quant text,vram_gb integer);
CREATE TABLE benchmark(model_id text PRIMARY KEY REFERENCES model,score integer NOT NULL);
CREATE TABLE supports(edge_id text PRIMARY KEY,variant_id text REFERENCES variant,runtime_id text REFERENCES runtime);
CREATE TABLE fits(edge_id text PRIMARY KEY,variant_id text REFERENCES variant,gpu_id text REFERENCES gpu);
"""
PG_INDEXES = """
CREATE INDEX model_provider ON model(provider_id);
CREATE INDEX model_base ON model(base_id);
CREATE INDEX model_role ON model(role_id);
CREATE INDEX variant_model ON variant(model_id);
CREATE INDEX benchmark_score ON benchmark(score DESC,model_id);
CREATE INDEX supports_runtime ON supports(runtime_id,variant_id);
CREATE INDEX fits_gpu ON fits(gpu_id,variant_id);
ANALYZE;
"""
SURREAL_SCHEMA = "\n".join(f"DEFINE TABLE {t} SCHEMALESS;" for t in TABLES[:-2]) + """
DEFINE TABLE supports TYPE RELATION IN variant OUT runtime SCHEMALESS;
DEFINE TABLE fits TYPE RELATION IN variant OUT gpu SCHEMALESS;
"""
SURREAL_INDEXES = """
DEFINE INDEX model_provider ON model FIELDS provider_ref;
DEFINE INDEX model_base ON model FIELDS base_ref;
DEFINE INDEX model_role ON model FIELDS role_ref;
DEFINE INDEX variant_model ON variant FIELDS model_ref;
DEFINE INDEX benchmark_score ON benchmark FIELDS score,model_ref;
DEFINE INDEX supports_runtime ON supports FIELDS out,in;
DEFINE INDEX fits_gpu ON fits FIELDS out,in;
"""


def pg_statements(data):
    # JSON input is generated locally. Identifiers and table names are closed.
    statements = []
    types = {
        "provider": "provider_id text,input_cost double precision", "role": "role_id text,min_score integer",
        "runtime": "runtime_id text,kind text", "gpu": "gpu_id text,vram_gb integer",
        "model": "model_id text,provider_id text,base_id text,name text,role_id text,embedding double precision[]",
        "variant": "variant_id text,model_id text,quant text,vram_gb integer",
        "benchmark": "model_id text,score integer", "supports": "edge_id text,variant_id text,runtime_id text",
        "fits": "edge_id text,variant_id text,gpu_id text"}
    for table in TABLES:
        for pos in range(0, len(data[table]), 250):
            raw = json.dumps(data[table][pos:pos+250], separators=(",", ":")).replace("'", "''")
            statements.append(f"INSERT INTO {table} SELECT * FROM jsonb_to_recordset('{raw}'::jsonb) AS x({types[table]});")
    return statements


def pg_load(data):
    return "BEGIN;\n"+"\n".join(pg_statements(data))+"\nCOMMIT;"


def surreal_load(data):
    def value(item, table):
        parts = []
        for key, val in item.items():
            target = {"provider_id": "provider", "base_id": "model", "role_id": "role", "model_id": "model"}.get(key)
            # Keep external IDs as strings AND declare explicit native links.
            parts.append(json.dumps(key) + ":" + json.dumps(val, separators=(",", ":")))
            if table == "model" and key in ("provider_id", "base_id", "role_id") or table == "variant" and key == "model_id":
                linked = "NONE" if val is None else target + ":" + val
                parts.append(key.replace("_id", "_ref") + ":" + linked)
        return "{" + ",".join(parts) + "}"
    statements = []
    primary = {"provider": "provider_id", "role": "role_id", "runtime": "runtime_id", "gpu": "gpu_id",
               "model": "model_id", "variant": "variant_id", "benchmark": "model_id"}
    for table in TABLES[:-2]:
        for pos in range(0, len(data[table]), 250):
            rows = []
            for item in data[table][pos:pos+250]:
                row = value(item, table)
                if table == "benchmark":
                    row = row[:-1] + ",model_ref:model:" + item["model_id"] + "}"
                rows.append("{id:"+table+":"+item[primary[table]]+","+row[1:])
            statements.append("INSERT INTO " + table + " [" + ",".join(rows) + "] RETURN NONE;")
    for table, target in (("supports", "runtime"), ("fits", "gpu")):
        for edge in data[table]:
            statements.append(f"RELATE variant:{edge['variant_id']}->{table}:{edge['edge_id']}->{target}:{edge[target+'_id']} RETURN NONE;")
    return statements


def queries():
    vector = "[" + ",".join(["1"] + ["0"]*15) + "]"
    pg_cos = "m.embedding[1]/sqrt((SELECT sum(v*v) FROM unnest(m.embedding) v))"
    su_cos = f"vector::similarity::cosine(embedding,{vector})"
    return {
        "provider_filter": ("SELECT model_id FROM model WHERE provider_id='p1' ORDER BY model_id LIMIT 20",
                            "SELECT model_id FROM model WHERE provider_ref=provider:p1 ORDER BY model_id LIMIT 20"),
        "base_quant": ("SELECT m.model_id,m.base_id AS base_model,v.quant FROM model m JOIN variant v USING(model_id) WHERE m.base_id IS NOT NULL ORDER BY m.model_id LIMIT 20",
                       "SELECT model_ref.model_id AS model_id,model_ref.base_ref.model_id AS base_model,quant FROM variant WHERE model_ref.base_ref != NONE ORDER BY model_id LIMIT 20"),
        "provider_cost": ("SELECT m.model_id,p.provider_id,p.input_cost FROM model m JOIN provider p USING(provider_id) ORDER BY m.model_id LIMIT 20",
                          "SELECT model_id,provider_ref.provider_id AS provider_id,provider_ref.input_cost AS input_cost FROM model ORDER BY model_id LIMIT 20"),
        "runtime_gpu": ("SELECT v.model_id FROM variant v JOIN supports s USING(variant_id) JOIN fits f USING(variant_id) WHERE s.runtime_id='r1' AND f.gpu_id='g0' ORDER BY v.model_id LIMIT 20",
                        "SELECT model_ref.model_id AS model_id FROM variant WHERE ->supports->runtime CONTAINS runtime:r1 AND ->fits->gpu CONTAINS gpu:g0 ORDER BY model_id LIMIT 20"),
        "role_candidate": ("SELECT m.model_id FROM model m JOIN role r USING(role_id) JOIN benchmark b USING(model_id) WHERE r.role_id='assistant' AND b.score>=r.min_score ORDER BY m.model_id LIMIT 20",
                           "SELECT model_ref.model_id AS model_id FROM benchmark WHERE model_ref.role_ref=role:assistant AND score>=model_ref.role_ref.min_score ORDER BY model_id LIMIT 20"),
        "local_benchmark": ("SELECT model_id,score FROM benchmark ORDER BY score DESC,model_id LIMIT 10",
                            "SELECT model_ref.model_id AS model_id,score FROM benchmark ORDER BY score DESC,model_id LIMIT 10"),
        "vector_exact": (f"SELECT m.model_id,{pg_cos} AS score FROM model m ORDER BY score DESC,m.model_id LIMIT 10",
                         f"SELECT model_id,{su_cos} AS score FROM model ORDER BY score DESC,model_id LIMIT 10"),
        "hybrid_exact": (f"SELECT m.model_id,.75*({pg_cos})+.25*CASE WHEN position('chat' in m.name)>0 THEN 1 ELSE 0 END AS score FROM model m ORDER BY score DESC,m.model_id LIMIT 10",
                         f"SELECT model_id,0.75*{su_cos}+(IF string::contains(name,'chat') {{ 0.25 }} ELSE {{ 0.0 }}) AS score FROM model ORDER BY score DESC,model_id LIMIT 10"),
    }


def normalize(rows):
    return [{k: round(v, 8) if isinstance(v, float) else v for k, v in row.items()} for row in rows]


def sql_batches(statements, *, max_bytes=512*1024, max_statements=150):
    """Bound encoded HTTP bodies, preserving statement order and completeness."""
    batch, size = [], 0
    for statement in statements:
        needed = len(statement.encode("utf-8"))+1
        if needed > max_bytes:
            raise ValueError("Individual synthetic SQL statement exceeds batch budget")
        if batch and (size+needed > max_bytes or len(batch) >= max_statements):
            yield "\n".join(batch)
            batch, size = [], 0
        batch.append(statement)
        size += needed
    if batch:
        yield "\n".join(batch)
