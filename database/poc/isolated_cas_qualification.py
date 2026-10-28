"""Synthetic CAS qualification only: new databases, no restore or performance run.

Invoked solely by the explicitly authorized isolated Docker controller, which
checks exact objects/resources and stops its two temporary containers in finally.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import secrets
import threading
import time

from discovery_cache import canonical_json, make_snapshot
from discovery_registry import discover_fixtures
from emit_discovery_import import emit_pg, emit_surreal, import_record, observation_time
from isolated_bench_clients import Postgres, Surreal
from isolated_bench_runtime import wait_for, surreal_ready
from isolated_docker_bench import docker, host_address, owned_metadata, save
from source_adapters import SourceRecord


def sql(snapshot, before, engine):
    stream = io.StringIO()
    (emit_pg if engine == "postgresql" else emit_surreal)(snapshot, stream, expected_snapshot=before)
    return stream.getvalue()


def rows(client, engine):
    data, _ = client.query("SELECT * FROM " + ("poc.discovery_cache" if engine == "postgresql" else "discovery_cache") + " ORDER BY record_key")
    return normalized(data)


def normalized(data):
    result = []
    for row in data:
        item = {k: v for k, v in row.items() if k != "id"}
        item["last_seen_at"] = observation_time(item["last_seen_at"])
        result.append(item)
    return sorted(result, key=lambda r: r["record_key"])


def fingerprint(data):
    return hashlib.sha256(canonical_json(data).encode()).hexdigest()


def run(root, attempt, objects, monitor):
    password = next(x.split("=", 1)[1] for x in (root/"surreal.private.env").read_text().splitlines() if x.startswith("SURREAL_PASS="))
    pg_host = host_address(owned_metadata(objects, "postgresql"), objects["campaign"]+"-net")
    su_host = host_address(owned_metadata(objects, "surrealdb"), objects["campaign"]+"-net")
    namespace = "cas_"+secrets.token_hex(5)
    database = "cas_"+secrets.token_hex(5)
    admin = wait_for(lambda: Postgres(pg_host), monitor)
    ready = wait_for(lambda: surreal_ready(su_host, namespace, password), monitor)
    try:
        versions = {"postgresql": admin.sql("SELECT version()")[0][0], "surrealdb": ready.request("GET", "/version")[1].decode()}
        ready.sql("DEFINE NAMESPACE "+namespace+"; DEFINE DATABASE "+database+";")
        admin.sql("CREATE DATABASE "+database)
    finally:
        admin.close()
        ready.close()
    pg = Postgres(pg_host, database)
    su = Surreal(su_host, namespace=namespace, database=database, password=password, session=True)
    before = discover_fixtures()
    original = canonical_json(before)
    records = [SourceRecord(**{k: v for k, v in r.items() if k not in {"record_key", "payload_sha256"}}) for r in before["records"]]
    omitted = next(r for r in records if r.source != "huggingface")
    observed = [r for r in records if r != omitted]
    def snapshot(revision, hour):
        changed = [replace(r, source_revision=revision,
                           attributes={**r.attributes, "cas_unknown": {"null": None, "false": False, "zero": 0, "empty": []}})
                   if r.source == "huggingface" else r for r in observed]
        return make_snapshot(changed, scope=before["scope"], captured_at=f"2026-10-28T{hour:02d}:00:00+00:00")
    a, b, c, d = (snapshot("synthetic-cas-"+label, hour) for label, hour in zip("abcd", (1, 2, 3, 4)))
    for name, value in (("baseline", before), ("a", a), ("b", b), ("c", c), ("d", d)):
        save(attempt/(name+".snapshot.synthetic.json"), value)
    def expected(snap):
        merged = {r["record_key"]: import_record(r, before) for r in before["records"]}
        merged.update({r["record_key"]: import_record(r, snap) for r in snap["records"]})
        return normalized(list(merged.values()))
    def psql(raw, label="synthetic_cas"):
        result = docker("exec", "-i", "-e", "PGAPPNAME="+label, objects["containers"]["postgresql"],
                        "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "bench", "-d", database,
                        data=raw.encode(), check=False, timeout=30)
        return result.returncode, b"Discovery CAS precondition failed" in result.stderr
    def su_import(raw, client=su):
        status, body, _ = client.request("POST", "/import", raw.encode(), allow_http_error=True)
        return status, b"Discovery CAS precondition failed" in body
    def require(ok, message):
        monitor.check()
        if not ok:
            raise RuntimeError(message)
    proof = {}
    try:
        pg.sql(Path(__file__).with_name("postgresql").joinpath("discovery_cache.sql").read_text())
        require(psql(sql(before, None, "postgresql"))[0] == 0, "PG baseline failed")
        require(su_import(sql(before, None, "surrealdb"))[0] == 200, "Surreal baseline failed")
        baseline = normalized([import_record(r, before) for r in before["records"]])
        for engine, client in (("postgresql", pg), ("surrealdb", su)):
            require(rows(client, engine) == baseline, "Baseline roundtrip differs")
        # Expected-absence must not overwrite an existing, different row.
        require(psql(sql(a, None, "postgresql")) == (3, True), "PG absence CAS failed")
        require(su_import(sql(a, None, "surrealdb")) == (422, True), "Surreal absence CAS failed")
        proof["expected_absence_rejected_existing"] = True
        require(rows(pg, "postgresql") == baseline and rows(su, "surrealdb") == baseline, "Absence failure changed state")

        def wait_pg(condition):
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                monitor.check()
                found, _ = pg.query("SELECT count(*) AS n FROM pg_stat_activity WHERE "+condition)
                if found[0]["n"] == 1:
                    return
                time.sleep(.01)
            raise RuntimeError("Expected PG concurrent writer phase was not observed")
        a_sql = sql(a, before, "postgresql").replace("DO $discovery_cas$", "SELECT pg_sleep(1.5);\nDO $discovery_cas$", 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(psql, a_sql, "synthetic_cas_a")
            wait_pg("application_name='synthetic_cas_a' AND wait_event='PgSleep'")
            second = pool.submit(psql, sql(b, before, "postgresql"), "synthetic_cas_b")
            wait_pg("application_name='synthetic_cas_b' AND wait_event_type='Lock'")
            require(first.result() == (0, False) and second.result() == (3, True), "PG race did not select one CAS writer")
        require(rows(pg, "postgresql") == expected(a), "PG concurrent loser changed state")
        proof["postgres_concurrency"] = {"committed": 1, "rejected": 1, "blocked_writer_observed": True, "loser_cas_error": True}

        barrier = threading.Barrier(2)
        def su_race(snap):
            client = Surreal(su_host, namespace=namespace, database=database, password=password, session=True)
            try:
                barrier.wait(timeout=5)
                raw = sql(snap, before, "surrealdb").replace("COMMIT TRANSACTION;", "SLEEP 500ms;\nCOMMIT TRANSACTION;")
                return su_import(raw, client)
            finally:
                client.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(su_race, a), pool.submit(su_race, b)
            outcomes = [first.result(), second.result()]
        require(sorted(status for status, _ in outcomes) == [200, 422], "Surreal concurrent transaction did not reject one writer")
        current = rows(su, "surrealdb")
        winner = a if current == expected(a) else b
        require(current == expected(winner), "Surreal race yielded mixed state")
        proof["surreal_concurrency"] = {"committed": 1, "rejected": 1, "coordinated_start": True,
                                        "concurrent_transaction_sleep_ms": 500, "winner_snapshot": winner["snapshot_id"]}
        # A later capture with an obsolete baseline MUST fail CAS, even though
        # the existing capture-time-only guard would allow this update.
        require(psql(sql(c, before, "postgresql")) == (3, True), "PG stale baseline CAS failed")
        require(su_import(sql(c, before, "surrealdb")) == (422, True), "Surreal stale baseline CAS failed")
        require(rows(pg, "postgresql") == expected(a) and rows(su, "surrealdb") == expected(winner), "CAS failure changed winners")
        proof["newer_capture_with_obsolete_baseline_rejected"] = True
        require(psql(sql(c, a, "postgresql"))[0] == 0, "PG reconciled baseline failed")
        require(su_import(sql(c, winner, "surrealdb"))[0] == 200, "Surreal reconciled baseline failed")
        require(psql(sql(c, a, "postgresql"))[0] == 0 and su_import(sql(c, winner, "surrealdb"))[0] == 200, "Already applied replay failed")
        require(rows(pg, "postgresql") == expected(c) and rows(su, "surrealdb") == expected(c), "Replay changed rows")
        proof["reconcile_and_replay_idempotent"] = True
        # Disconnect psql with an open transaction; inject an error after the
        # first Surreal upsert. Both must retain the preceding committed state.
        require(psql(sql(d, c, "postgresql").rsplit("COMMIT;", 1)[0])[0] == 0, "PG interrupted transaction failed unexpectedly")
        raw = sql(d, c, "surrealdb")
        first_upsert = next(line for line in raw.splitlines() if line.startswith("UPSERT "))
        broken = raw.replace(first_upsert, first_upsert+"\nTHROW 'synthetic-cas-interruption';", 1)
        require(su_import(broken)[0] == 422, "Surreal failure injection not rejected")
        require(rows(pg, "postgresql") == expected(c) and rows(su, "surrealdb") == expected(c), "Interrupted CAS leaked changes")
        require(psql(sql(d, c, "postgresql"))[0] == 0 and su_import(sql(d, c, "surrealdb"))[0] == 200, "CAS retry failed")
        require(rows(pg, "postgresql") == expected(d) and rows(su, "surrealdb") == expected(d), "CAS retry lost data")
        proof["failure_atomicity_and_retry"] = True
        proof["not_observed_preserved"] = len(rows(pg, "postgresql")) == len(before["records"]) == 7
        proof["input_snapshots_unchanged"] = canonical_json(before) == original
        require(proof["not_observed_preserved"] and proof["input_snapshots_unchanged"], "B2 non-deletion or immutability failed")
        # A matching stored digest alone is not enough: compare full row data.
        target = next(r for r in d["records"] if r["source"] == "huggingface")
        damaged = json.loads(canonical_json(target["attributes"]))
        damaged["cas_unknown"]["false"] = 0
        def set_attributes(value):
            encoded = canonical_json(value)
            pg.sql("UPDATE poc.discovery_cache SET attributes='"+encoded.replace("'", "''")+"'::jsonb WHERE record_key='"+target["record_key"]+"'")
            su.sql("UPDATE discovery_cache:"+target["record_key"]+" SET attributes="+encoded+" RETURN NONE;")
        set_attributes(damaged)
        corrupt_rows = rows(pg, "postgresql")
        require(corrupt_rows == rows(su, "surrealdb"), "Corruption fixture differs across engines")
        e = snapshot("synthetic-cas-e", 6)
        require(psql(sql(e, d, "postgresql")) == (3, True), "PG full-row CAS missed corruption")
        require(su_import(sql(e, d, "surrealdb")) == (422, True), "Surreal full-row CAS missed corruption")
        require(rows(pg, "postgresql") == corrupt_rows and rows(su, "surrealdb") == corrupt_rows, "Rejected corruption CAS changed state")
        # Restore ONLY this newly created synthetic test row, not historical data.
        set_attributes(target["attributes"])
        proof["full_row_cas_rejects_bool_zero_corruption"] = True

        template = next(r for r in records if r.source == "models.dev")
        special = [replace(template, source_id="synthetic/cas-null-revision", source_revision=None),
                   replace(template, source_id="synthetic/cas-empty-revision", source_revision="")]
        special_scope = {"models.dev": {"mode": "exact_ids", "ids": [r.source_id for r in special]}}
        nullable = make_snapshot(special, scope=special_scope, captured_at="2026-10-28T05:00:00+00:00")
        require(psql(sql(nullable, None, "postgresql"))[0] == 0 and su_import(sql(nullable, None, "surrealdb"))[0] == 200, "Nullable revisions import failed")
        require(psql(sql(nullable, None, "postgresql"))[0] == 0 and su_import(sql(nullable, None, "surrealdb"))[0] == 200, "Nullable revisions replay failed")
        all_expected = normalized(expected(d)+[import_record(r, nullable) for r in nullable["records"]])
        require(rows(pg, "postgresql") == all_expected and rows(su, "surrealdb") == all_expected, "Empty revision collapsed into null")
        proof["empty_and_null_revisions_preserved"] = True

        absent = [replace(template, source_id="synthetic/missing-current"), replace(template, source_id="synthetic/missing-peer")]
        absent_scope = {"models.dev": {"mode": "exact_ids", "ids": [r.source_id for r in absent]}}
        missing_before = make_snapshot(absent[:1], scope=absent_scope, captured_at="2026-10-28T05:00:00+00:00")
        missing_after = make_snapshot(absent, scope=absent_scope, captured_at="2026-10-28T06:00:00+00:00")
        require(psql(sql(missing_after, missing_before, "postgresql")) == (3, True), "PG expected-present absence was not rejected")
        require(su_import(sql(missing_after, missing_before, "surrealdb")) == (422, True), "Surreal expected-present absence was not rejected")
        require(rows(pg, "postgresql") == all_expected and rows(su, "surrealdb") == all_expected, "Missing-row CAS leaked a new peer")
        proof["expected_present_missing_row_rejected"] = True
        proof["final_records"] = len(all_expected)
        proof["final_fingerprint_sha256"] = fingerprint(rows(pg, "postgresql"))
        monitor.sample()
        save(attempt/"cas_qualification.json", proof)
        return {"mode": "synthetic_cas_only", "versions": versions, "database": database, "namespace": namespace,
                "cas": proof, "restorations_performed": False, "performance_campaign": False,
                "historical_poc_databases_queried": False, "provider_network_calls": False}
    finally:
        pg.close()
        su.close()
