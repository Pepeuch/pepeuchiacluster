"""Actual synthetic engine qualification, invoked only by the isolated controller.

Fixtures never become real provider observations. No production import executor.
"""

from dataclasses import replace
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import time

from isolated_bench_clients import EngineError, Postgres, Surreal
from confirmed_sql_batches import DeliveryInterrupted, plan as batch_plan
from isolated_bench_ingestion import PG_RECEIPTS, SU_RECEIPTS, ingest, transaction
from isolated_bench_plans import postgres_plan, surreal_plan
from isolated_bench_workload import (PG_INDEXES, PG_SCHEMA, SIZES, SURREAL_INDEXES, SURREAL_SCHEMA,
                                     TABLES, corpus, expected, normalize, pg_load, pg_statements, queries, surreal_load)
from isolated_docker_bench import command, docker, event, host_address, owned_metadata, save


def write(path, data):
    raw = data.encode() if isinstance(data, str) else data
    with path.open("xb") as stream:
        stream.write(raw)
    return {"file": path.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def percentile(samples, p):
    return sorted(samples)[max(0, math.ceil(len(samples)*p)-1)]


def wait_for(factory, monitor):
    start = time.monotonic()
    while True:
        monitor.check()
        try:
            client = factory()
            return client
        except (OSError, EngineError):
            if time.monotonic()-start > 60:
                raise RuntimeError("Engine startup readiness exceeded 60 seconds") from None
            time.sleep(.5)


def schema_hash(client, engine):
    # Logical content hash; omit Surreal's system record id while retaining
    # explicit links and typed relation endpoints in canonical string form.
    all_rows = {}
    for table in TABLES:
        if engine == "postgresql":
            rows, _ = client.query("SELECT * FROM "+table+" ORDER BY 1")
        else:
            rows, _ = client.query("SELECT * FROM "+table+" ORDER BY id")
        all_rows[table] = rows
    counts = {t:len(r) for t,r in all_rows.items()}
    receipts, _ = client.query("SELECT * FROM bench_batch_receipt ORDER BY batch_id")
    all_rows["bench_batch_receipt"] = receipts
    raw = json.dumps(all_rows, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "counts": counts, "receipt_count": len(receipts)}


def run_queries(pg, su, data, mode, destination, monitor):
    if su.auth_mode != "bearer_session":
        raise RuntimeError("Comparable measurements require a pre-authenticated Surreal session")
    result = {}
    oracle = expected(data)
    for name, pair in queries().items():
        monitor.check()
        item = {"expected": oracle[name], "engines": {}}
        for engine, client, sql in (("postgresql", pg, pair[0]), ("surrealdb", su, pair[1])):
            actual, duration = client.query(sql)
            if normalize(actual) != oracle[name]:
                save(destination/(mode+"-"+name+"-"+engine+"-mismatch.json"), {"expected": oracle[name], "actual": normalize(actual), "sql": sql})
                raise RuntimeError("Functional parity failed: "+engine+" "+name)
            for _ in range(3):
                client.query(sql)
            item["engines"][engine] = {"first_call_ms": duration, "samples_ms": [], "sql": sql,
                                        "timing_scope": "persistent_client_wall", "cache_state": "warm", "server_times_raw": [],
                                        "authentication_profile":"postgres_native_trust" if engine=="postgresql" else su.auth_mode}
        for repetition in range(15):
            operations = [("postgresql", pg, pair[0]), ("surrealdb", su, pair[1])]
            if repetition % 2:
                operations.reverse()
            for engine, client, sql in operations:
                rows, duration = client.query(sql)
                if normalize(rows) != oracle[name]:
                    raise RuntimeError("Repeated query result changed: "+engine+" "+name)
                item["engines"][engine]["samples_ms"].append(duration)
                if engine == "surrealdb":
                    item["engines"][engine]["server_times_raw"].extend(client.last_server_times)
        for engine, client, sql in (("postgresql", pg, pair[0]), ("surrealdb", su, pair[1])):
            measured = item["engines"][engine]
            measured["p50_ms"] = percentile(measured["samples_ms"], .5)
            measured["p95_ms"] = percentile(measured["samples_ms"], .95)
            if engine == "postgresql":
                start = time.perf_counter()
                response = json.loads(pg.sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "+sql)[0][0])
                plan = postgres_plan(response, expected_rows=len(oracle[name]))
                plan["request_client_wall_ms"] = (time.perf_counter()-start)*1000
            else:
                response, wall = su.sql(sql+" EXPLAIN FULL;")
                plan = surreal_plan(response, expected_rows=len(oracle[name]))
                plan["request_client_wall_ms"] = wall
            measured["plan_measurement"] = plan
            measured["query_measurement_scope"] = "regular_execution_excludes_explain_samples"
        result[name] = item
        event(monitor.root, "query_verified", size=data["size"], mode=mode, query=name,
              pg_p95_ms=item["engines"]["postgresql"]["p95_ms"], surreal_p95_ms=item["engines"]["surrealdb"]["p95_ms"])
    save(destination/(mode+"-queries.json"), result)
    return result


def load_batches(client, factory, engine, statements, destination, monitor, *, qualify_interruption):
    batches = batch_plan(statements,max_statements=3 if qualify_interruption else 150)
    request_sizes = {b.batch_id:len(transaction(engine,b).encode("utf-8")) for b in batches}
    save(destination/(engine+"-batch-plan.json"), {"batches":[{**b.receipt(),"request_body_bytes":request_sizes[b.batch_id]} for b in batches],"max_encoded_body_bytes":512*1024})
    journal = destination/(engine+"-batch-receipts.jsonl")
    def receipt(value):
        monitor.check()
        with journal.open("a",encoding="utf-8") as stream:
            stream.write(json.dumps({**value,"request_body_bytes":request_sizes[value["batch_id"]]},sort_keys=True)+"\n")
            stream.flush()
            os.fsync(stream.fileno())
    proof = {"interrupted_between_batches":False,"qualification_overhead_in_load_time":qualify_interruption}
    if qualify_interruption:
        try:
            ingest(client,engine,batches,on_receipt=receipt,interrupt_after=1)
        except DeliveryInterrupted:
            prefix = schema_hash(client,engine)
            client.close()
            client = factory()  # New connection; only DB receipts establish resume.
            if schema_hash(client,engine) != prefix:
                raise RuntimeError("Acknowledged prefix lost on client reconnection")
            try:
                client.sql(transaction(engine,batches[1],inject_failure=True))
            except EngineError as exc:
                if engine=="postgresql":
                    if exc.code != "22012":
                        raise
                    client.sql("ROLLBACK;")
                elif exc.code != "surreal_sql_error":
                    raise
            else:
                raise RuntimeError("Injected atomic batch failure unexpectedly succeeded")
            if schema_hash(client,engine) != prefix:
                raise RuntimeError("Failed batch modified acknowledged prefix or data")
            proof.update(interrupted_between_batches=True,first_committed_batch=batches[0].receipt(),
                         next_batch_rolled_back=True,reconnected=True)
        else:
            raise RuntimeError("Between-batch interruption did not occur")
    proof["resume"] = ingest(client,engine,batches,on_receipt=receipt)
    if qualify_interruption:
        complete = schema_hash(client,engine)
        proof["second_resume"] = ingest(client,engine,batches,on_receipt=receipt)
        if schema_hash(client,engine)!=complete or proof["second_resume"]["applied"]!=0:
            raise RuntimeError("Complete batch replay changed data")
        proof["complete_content_stable_on_replay"] = True
    save(destination/(engine+"-batch-ingestion.json"),proof)
    return client,proof


def restore_stage(root, destination, objects, pg, su, pg_host, su_host, database, namespace, password, monitor):
    before_pg, before_su = schema_hash(pg, "postgresql"), schema_hash(su, "surrealdb")
    start = time.perf_counter()
    dump = docker("exec", objects["containers"]["postgresql"], "pg_dump", "-U", "bench", "-d", database, "-Fc", timeout=120).stdout
    pg_dump = write(destination/"postgres.dump", dump)
    pg_dump["elapsed_ms"] = (time.perf_counter()-start)*1000
    restored_name = database+"_restore"
    pg.sql("CREATE DATABASE "+restored_name)
    start = time.perf_counter()
    docker("exec", "-i", objects["containers"]["postgresql"], "pg_restore", "--exit-on-error", "-U", "bench", "-d", restored_name, data=dump, timeout=120)
    pg_dump["restore_ms"] = (time.perf_counter()-start)*1000
    restored_pg = Postgres(pg_host, restored_name)
    try:
        after_pg = schema_hash(restored_pg, "postgresql")
    finally:
        restored_pg.close()
    if after_pg != before_pg:
        raise RuntimeError("PostgreSQL restore content differs")
    _, raw, elapsed = su.request("GET", "/export")
    # Never let a backup change the header-selected new restoration target.
    if re.search(rb"(?im)^\s*USE\b", raw) or password.encode() in raw:
        raise RuntimeError("Unexpected target selection or credential in synthetic export")
    su_dump = write(destination/"surreal.surql", raw)
    su_dump["elapsed_ms"] = elapsed
    restored_su = Surreal(su_host, namespace=namespace, database=restored_name, password=password, session=True)
    try:
        restored_su.sql("DEFINE DATABASE "+restored_name+";")
        status, _, restore_ms = restored_su.request("POST", "/import", raw)
        after_su = schema_hash(restored_su, "surrealdb")
    finally:
        restored_su.close()
    su_dump["restore_ms"] = restore_ms
    if after_su != before_su:
        raise RuntimeError("SurrealDB restore content differs")
    monitor.check()
    report = {"postgresql": {"backup": pg_dump, "before": before_pg, "restored": after_pg, "target": restored_name},
              "surrealdb": {"backup": su_dump, "before": before_su, "restored": after_su, "target": restored_name},
              "source_destinations_distinct": True, "physical_crash_recovery_tested": False}
    save(destination/"restore.json", report)
    return report


def discovery_qualification(root, destination, objects, pg_host, su_host, namespace, password, monitor):
    from copy import deepcopy
    from datetime import datetime
    from discovery_cache import canonical_json, compare_snapshots, make_snapshot
    from discovery_registry import discover_fixtures
    from emit_discovery_import import emit_pg, emit_surreal, import_record
    from source_adapters import SourceRecord

    database = "discovery_"+secrets.token_hex(4)
    admin = Postgres(pg_host)
    admin.sql("CREATE DATABASE "+database)
    admin.close()
    pg = Postgres(pg_host, database)
    su = Surreal(su_host, namespace=namespace, database=database, password=password, session=True)
    checks = {}
    snapshot = discover_fixtures()
    original = deepcopy(snapshot)
    records = [SourceRecord(**{k: v for k, v in r.items() if k not in {"record_key", "payload_sha256"}}) for r in snapshot["records"]]
    changed = list(records)
    index = next(i for i, r in enumerate(changed) if r.source == "huggingface")
    changed[index] = replace(changed[index], source_revision="synthetic-r2",
                             attributes={**changed[index].attributes, "bench_unknown": {"null": None, "false": False, "zero": 0, "empty": []}})
    after = make_snapshot(changed, scope=snapshot["scope"], captured_at="2026-10-28T12:00:00+00:00")
    # A raw partial B2 observation tests non-deletion only. It is NOT promoted
    # to a complete B4 cache or controlled provider observation.
    partial = make_snapshot(changed[:-1], scope=snapshot["scope"], captured_at="2026-10-28T13:00:00+00:00")
    for label, snap in (("baseline", snapshot), ("revision", after), ("partial", partial)):
        save(destination/(label+".snapshot.synthetic.json"), snap)
    def psql(raw, expected_failure=False):
        result = docker("exec", "-i", objects["containers"]["postgresql"], "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "bench", "-d", database,
                        data=raw.encode(), check=False, timeout=60)
        if expected_failure != (result.returncode != 0):
            raise RuntimeError("Unexpected psql import outcome")
        return result.returncode
    def emit(snap, engine):
        output = io.StringIO()
        (emit_pg if engine == "postgresql" else emit_surreal)(snap, output)
        return output.getvalue()
    def surreal_import(raw):
        status, body, _ = su.request("POST", "/import", raw.encode(), allow_http_error=True)
        if status >= 400:
            # Private synthetic query diagnostic, NEVER headers or credentials.
            if password.encode() in body:
                raise RuntimeError("Refused sensitive import diagnostic")
            save(destination/("surreal-import-error-"+secrets.token_hex(4)+".json"),
                 {"status": status, "body": body.decode(errors="replace")[:16000], "synthetic": True})
            raise RuntimeError("Synthetic Surreal import failed; bounded diagnostic retained")
    def read(engine, active=None):
        active = (pg if engine=="postgresql" else su) if active is None else active
        if engine == "postgresql":
            rows, _ = active.query("SELECT * FROM poc.discovery_cache ORDER BY record_key")
            for row in rows:
                row["last_seen_at"] = datetime.fromisoformat(row["last_seen_at"]).isoformat(timespec="seconds")
        else:
            rows, _ = active.query("SELECT * FROM discovery_cache ORDER BY record_key")
            rows = [{k: v for k, v in row.items() if k != "id"} for row in rows]
        return rows
    try:
        pg.sql(Path(__file__).with_name("postgresql").joinpath("discovery_cache.sql").read_text())
        pg.sql("CREATE TABLE poc.external_models(id text PRIMARY KEY); INSERT INTO poc.external_models VALUES ('synthetic-preserved-sentinel')")
        su.sql("DEFINE DATABASE "+database+"; UPSERT external_models:sentinel CONTENT {marker:'synthetic-preserved-sentinel'};")
        psql(emit(snapshot, "postgresql"))
        surreal_import(emit(snapshot, "surrealdb"))
        baseline = sorted((import_record(r, snapshot) for r in snapshot["records"]), key=lambda r: r["record_key"])
        for engine in ("postgresql", "surrealdb"):
            if canonical_json(read(engine)) != canonical_json(baseline):
                raise RuntimeError("B2 baseline roundtrip differs: "+engine)
        checks["seven_source_roundtrip"] = {"verified": True, "count": len(baseline), "synthetic": True}
        psql(emit(snapshot, "postgresql"))
        surreal_import(emit(snapshot, "surrealdb"))
        if read("postgresql") != baseline or read("surrealdb") != baseline:
            raise RuntimeError("Repeated B2 import changed data")
        checks["initial_reimport_idempotent"] = True
        broken = emit(after, "postgresql").replace("COMMIT;", "SELECT 1/0;\nCOMMIT;")
        failure_code = psql(broken, expected_failure=True)
        if read("postgresql") != baseline:
            raise RuntimeError("PostgreSQL failed import was not atomic")
        checks["pg_failed_import_rolled_back"] = {"verified": True, "psql_exit": failure_code, "injection": "before_commit_division_by_zero"}
        # A real open transaction is disconnected before COMMIT; no container kill.
        interrupted = Postgres(pg_host, database)
        interrupted.sql("BEGIN; UPDATE poc.discovery_cache SET display_name='synthetic-interrupted';")
        interrupted.close()
        time.sleep(.2)
        if read("postgresql") != baseline:
            raise RuntimeError("PostgreSQL disconnected transaction leaked changes")
        checks["pg_tcp_disconnect_rolled_back"] = True
        raw = emit(after, "surrealdb")
        statements = [line for line in raw.splitlines() if line.startswith("UPSERT ")]
        failing = "OPTION IMPORT;\n"+statements[0]+"\nTHROW 'synthetic-injected-failure';\n"
        status, _, _ = su.request("POST", "/import", failing.encode(), allow_http_error=True)
        partial_rows = read("surrealdb")
        prefix_changed = sum(a != b for a, b in zip(partial_rows, baseline))
        if status < 400 or prefix_changed != 1:
            raise RuntimeError("Unexpected SurrealDB partial import semantics")
        checks["surreal_failed_import_prefix_persisted"] = {"verified": True, "http_status": status, "changed_rows": prefix_changed}
        # Delivery interrupted after one acknowledged instruction, then replayed.
        su.request("POST", "/import", ("OPTION IMPORT;\n"+statements[0]+"\n").encode())
        checks["surreal_delivery_stopped_after_acknowledged_prefix"] = read("surrealdb") == partial_rows
        psql(emit(after, "postgresql"))
        su.request("POST", "/import", raw.encode())
        revised = sorted((import_record(r, after) for r in after["records"]), key=lambda r: r["record_key"])
        for engine in ("postgresql", "surrealdb"):
            if canonical_json(read(engine)) != canonical_json(revised):
                raise RuntimeError("Revision import differs: "+engine)
        psql(emit(after, "postgresql"))
        su.request("POST", "/import", raw.encode())
        checks["revision_and_retry"] = {"verified": read("postgresql") == revised and read("surrealdb") == revised,
                                          "diff": compare_snapshots(snapshot, after), "remote_revision_observed": False}
        psql(emit(partial, "postgresql"))
        su.request("POST", "/import", emit(partial, "surrealdb").encode())
        expected_partial = {r["record_key"]: r for r in revised}
        expected_partial.update({r["record_key"]: import_record(r, partial) for r in partial["records"]})
        expected_partial = [expected_partial[k] for k in sorted(expected_partial)]
        if canonical_json(read("postgresql")) != canonical_json(expected_partial) or canonical_json(read("surrealdb")) != canonical_json(expected_partial):
            raise RuntimeError("Partial observation deleted or replaced an unobserved record")
        checks["not_observed_never_deleted"] = {"verified": True, "diff": compare_snapshots(after, partial)}
        # Stale replacement guard prototype, explicitly outside legacy emitters.
        target = expected_partial[0]
        key = target["record_key"]
        pg.sql("UPDATE poc.discovery_cache SET display_name='must-not-apply' WHERE record_key='"+key+"' AND payload_sha256='"+"0"*64+"';")
        su.sql("UPDATE discovery_cache:"+key+" SET display_name='must-not-apply' WHERE payload_sha256='"+"0"*64+"' RETURN NONE;")
        if canonical_json(read("postgresql")) != canonical_json(expected_partial) or canonical_json(read("surrealdb")) != canonical_json(expected_partial):
            raise RuntimeError("CAS mismatch changed data")
        checks["cas_wrong_payload_rejected"] = {"verified": True, "legacy_emitters_guarded": False, "full_executor_implemented": False}
        # This run qualifies regenerated SQL only. Retained v6 artifacts and
        # bundles still document the historical unguarded overwrite faithfully.
        guarded = []
        def refuse(snap, label):
            monitor.check()
            code = psql(emit(snap, "postgresql"), expected_failure=True)
            status, body, _ = su.request("POST", "/import", emit(snap, "surrealdb").encode(), allow_http_error=True)
            if status < 400 or b"Discovery observation is stale or conflicting" not in body:
                raise RuntimeError("Surreal import did not report the expected replay guard")
            for engine in ("postgresql", "surrealdb"):
                if canonical_json(read(engine)) != canonical_json(expected_partial):
                    raise RuntimeError("Refused snapshot changed stored rows: " + engine)
            guarded.append({"case": label, "postgres_exit": code, "surreal_http_status": status,
                            "both_engines_unchanged": True})
        refuse(snapshot, "old_revision_replay")
        older_equal = deepcopy(partial)
        older_equal["captured_at"] = "2026-10-28T12:59:59+00:00"
        refuse(older_equal, "old_identical_payload_must_not_rewind_time")
        conflicting = list(changed[:-1])
        conflicting[-1] = replace(conflicting[-1], display_name="Synthetic same-instant conflict")
        # Include an absent row in the rejected transaction: it must NOT leak.
        conflicting.append(replace(changed[0], source_id="synthetic/must-not-leak"))
        same_time = make_snapshot(conflicting, scope=partial["scope"], captured_at=partial["captured_at"])
        refuse(same_time, "same_instant_conflict_with_new_row_atomic_rollback")
        offset_equal = deepcopy(partial)
        offset_equal["captured_at"] = "2026-10-28T15:00:00+02:00"
        psql(emit(offset_equal, "postgresql"))
        su.request("POST", "/import", emit(offset_equal, "surrealdb").encode())
        # Restore the original spelling at the SAME instant, also a valid replay.
        psql(emit(partial, "postgresql"))
        su.request("POST", "/import", emit(partial, "surrealdb").encode())
        for engine in ("postgresql", "surrealdb"):
            if canonical_json(read(engine)) != canonical_json(expected_partial):
                raise RuntimeError("Equivalent-instant idempotent replay differs: " + engine)
        checks["regenerated_sql_replay_guard"] = {"cases": guarded, "equivalent_timezone_replay": True,
                                                  "old_pre_generated_sql_protected": False,
                                                  "capture_is_provider_revision_order": False,
                                                  "concurrent_engine_transactions_tested": False}
        same_name = [replace(next(r for r in records if r.source==source),source_id="synthetic/shared-name",display_name="Same synthetic display name")
                     for source in ("huggingface","modelscope")]
        pair = make_snapshot(same_name,scope={r.source:{"mode":"exact_ids","ids":[r.source_id]} for r in same_name},captured_at="2026-10-28T14:00:00+00:00")
        save(destination/"same-name-pair.snapshot.synthetic.json",pair)
        psql(emit(pair,"postgresql"))
        su.request("POST","/import",emit(pair,"surrealdb").encode())
        for engine in ("postgresql","surrealdb"):
            found=[r for r in read(engine) if r["source_id"]=="synthetic/shared-name"]
            if len(found)!=2 or len({r["record_key"] for r in found})!=2 or {r["source"] for r in found}!={"huggingface","modelscope"}:
                raise RuntimeError("Same-name resources were merged across platforms")
        checks["same_name_cross_platform_identity_preserved"] = True
        kinds=sorted({r["entity_type"] for r in read("postgresql")})
        if kinds!=["agent_resource","inference_endpoint","model_artifact","model_reference","nim_microservice"]:
            raise RuntimeError("Resource types were conflated")
        checks["five_resource_types_distinct"] = kinds
        try:
            compare_snapshots(snapshot,pair)
        except ValueError:
            checks["incompatible_scope_comparison_refused"]=True
        else:
            raise RuntimeError("Different scopes were compared as missing resources")
        sentinel_pg, _ = pg.query("SELECT id FROM poc.external_models")
        sentinel_su, _ = su.query("SELECT marker FROM external_models")
        if sentinel_pg != [{"id": "synthetic-preserved-sentinel"}] or sentinel_su != [{"marker": "synthetic-preserved-sentinel"}]:
            raise RuntimeError("Synthetic historical table sentinel changed")
        checks["unrelated_table_preserved"] = True
        checks["snapshot_inputs_unchanged"] = snapshot == original
        # Restore this B2 cache, unknown values and explicit relationships too.
        final_pg, final_su = read("postgresql"), read("surrealdb")
        if canonical_json(final_pg)!=canonical_json(final_su):
            raise RuntimeError("Final B2 parity differs")
        dump=docker("exec",objects["containers"]["postgresql"],"pg_dump","-U","bench","-d",database,"-Fc",timeout=60).stdout
        pg_artifact=write(destination/"discovery-postgres.dump",dump)
        restored_name=database+"_restore"
        pg.sql("CREATE DATABASE "+restored_name)
        docker("exec","-i",objects["containers"]["postgresql"],"pg_restore","--exit-on-error","-U","bench","-d",restored_name,data=dump,timeout=60)
        restored_pg=Postgres(pg_host,restored_name)
        try:
            restored_pg_rows=read("postgresql",restored_pg)
        finally:
            restored_pg.close()
        _,exported,_=su.request("GET","/export")
        if re.search(rb"(?im)^\s*USE\b",exported) or password.encode() in exported:
            raise RuntimeError("Unsafe target or credential in B2 export")
        su_artifact=write(destination/"discovery-surreal.surql",exported)
        restored_su=Surreal(su_host,namespace=namespace,database=restored_name,password=password,session=True)
        try:
            restored_su.sql("DEFINE DATABASE "+restored_name+";")
            restored_su.request("POST","/import",exported)
            restored_su_rows=read("surrealdb",restored_su)
        finally:
            restored_su.close()
        if canonical_json(restored_pg_rows)!=canonical_json(final_pg) or canonical_json(restored_su_rows)!=canonical_json(final_su):
            raise RuntimeError("B2 restored content differs")
        checks["b2_restore_new_destinations"]={"verified":True,"records":len(final_pg),"target":restored_name,"postgres":pg_artifact,"surreal":su_artifact}
        save(destination/"discovery_qualification.json", checks)
        monitor.check()
        return checks
    finally:
        pg.close()
        su.close()


def run(root, attempt, objects, monitor, *, qualification_only=False):
    password = next(line.split("=", 1)[1] for line in (root/"surreal.private.env").read_text().splitlines() if line.startswith("SURREAL_PASS="))
    namespace = "bench_"+secrets.token_hex(5)
    pg_host = host_address(owned_metadata(objects, "postgresql"), objects["campaign"]+"-net")
    su_host = host_address(owned_metadata(objects, "surrealdb"), objects["campaign"]+"-net")
    admin = wait_for(lambda: Postgres(pg_host), monitor)
    ready_su = wait_for(lambda: surreal_ready(su_host, namespace, password), monitor)
    version_pg = admin.sql("SELECT version()")[0][0]
    version_su = ready_su.request("GET", "/version")[1].decode()
    ready_su.sql("DEFINE NAMESPACE "+namespace+";")
    ready_su.close()
    versions = {"postgresql": version_pg, "surrealdb": version_su}
    save(attempt/"versions.json", versions)
    stages = []
    for size in (() if qualification_only else SIZES):
        monitor.check()
        destination = attempt/str(size)
        destination.mkdir(mode=0o700)
        data = corpus(size)
        corpus_artifact = write(destination/"corpus.synthetic.json", json.dumps(data, sort_keys=True, separators=(",", ":")))
        database = "stage_"+secrets.token_hex(4)+"_"+str(size)
        admin.sql("CREATE DATABASE "+database)
        pg = Postgres(pg_host, database)
        su = Surreal(su_host, namespace=namespace, database=database, password=password, session=True)
        try:
            pg.sql(PG_SCHEMA+PG_RECEIPTS)
            su.sql("DEFINE DATABASE "+database+";"+SURREAL_SCHEMA+SU_RECEIPTS)
            pg_sql, su_statements = pg_load(data), surreal_load(data)
            write(destination/"postgres-load.sql", PG_SCHEMA+"\n"+pg_sql)
            write(destination/"surreal-load.surql", SURREAL_SCHEMA+"\n"+"\n".join(su_statements))
            start = time.perf_counter()
            pg, pg_batch_proof = load_batches(pg,lambda:Postgres(pg_host,database),"postgresql",pg_statements(data),destination,monitor,qualify_interruption=size==30)
            load_pg = (time.perf_counter()-start)*1000
            start = time.perf_counter()
            su, su_batch_proof = load_batches(su,lambda:Surreal(su_host,namespace=namespace,database=database,password=password,session=True),"surrealdb",su_statements,destination,monitor,qualify_interruption=size==30)
            load_su = (time.perf_counter()-start)*1000
            counts_pg, counts_su = schema_hash(pg, "postgresql"), schema_hash(su, "surrealdb")
            if counts_pg["counts"] != counts_su["counts"] or counts_pg["counts"]["model"] != size:
                raise RuntimeError("Imported synthetic table counts differ")
            stage = {"size": size, "database": database, "namespace": namespace, "corpus": corpus_artifact,
                     "load_ms": {"postgresql": load_pg, "surrealdb": load_su}, "counts": counts_pg["counts"],
                     "batch_ingestion":{"postgresql":pg_batch_proof,"surrealdb":su_batch_proof}}
            event(root, "stage_loaded", size=size, pg_load_ms=load_pg, surreal_load_ms=load_su)
            stage["baseline"] = run_queries(pg, su, data, "baseline", destination, monitor)
            pg.sql(PG_INDEXES)
            su.sql(SURREAL_INDEXES)
            write(destination/"postgres-indexes.sql", PG_INDEXES)
            write(destination/"surreal-indexes.surql", SURREAL_INDEXES)
            stage["additional_indexes"] = run_queries(pg, su, data, "additional_indexes", destination, monitor)
            stage["restore"] = restore_stage(root, destination, objects, pg, su, pg_host, su_host, database, namespace, password, monitor)
            save(destination/"stage.json", stage)
            stages.append({"size": size, "database": database, "status": "VERIFIED", "artifact_directory": str(destination)})
            monitor.sample()  # Resource gate before advancing to the next size.
            event(root, "stage_verified", size=size)
        finally:
            pg.close()
            su.close()
    admin.close()
    discovery_dir = attempt/"discovery"
    discovery_dir.mkdir(mode=0o700)
    discovery = discovery_qualification(root, discovery_dir, objects, pg_host, su_host, namespace, password, monitor)
    return {"versions": versions, "stages": stages, "discovery": discovery,
            "mode": "b2_qualification_only" if qualification_only else "performance_and_b2",
            "timing_scope": "persistent_client_wall", "cold_os_cache_tested": False, "ann_tested": False,
            "authentication_profiles":{"postgresql":"postgres_native_trust","surrealdb":"bearer_session"},
            "historical_poc_databases_queried": False, "provider_network_calls": False}


def surreal_ready(host, namespace, password):
    client = Surreal(host, namespace=namespace, database="readiness", password=password, timeout=5)
    try:
        client.request("GET", "/ready")
        client.authenticate(password)
        return client
    except BaseException:
        client.close()
        raise
