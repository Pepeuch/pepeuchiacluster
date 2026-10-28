"""Atomic, receipt-confirmed batches for synthetic benchmark databases only."""

import json

from confirmed_sql_batches import MAX_BODY_BYTES, manifest_sha256, deliver


FIELDS = "batch_id,payload_sha256,seq_no,body_bytes"
PG_RECEIPTS = "CREATE TABLE bench_batch_receipt(batch_id text PRIMARY KEY,payload_sha256 text NOT NULL,seq_no integer NOT NULL,body_bytes integer NOT NULL);"
SU_RECEIPTS = "DEFINE TABLE bench_batch_receipt SCHEMALESS;"


def insert_receipt(engine, receipt):
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    if engine == "postgresql":
        return ("INSERT INTO bench_batch_receipt SELECT * FROM jsonb_to_record('"+raw+"'::jsonb) AS x("
                "batch_id text,payload_sha256 text,seq_no integer,body_bytes integer);")
    if engine == "surrealdb":
        return "CREATE bench_batch_receipt:"+receipt["batch_id"]+" CONTENT "+raw+" RETURN NONE;"
    raise ValueError("Closed synthetic engine selection required")


def transaction(engine, batch, *, inject_failure=False):
    failure = "SELECT 1/0;" if engine == "postgresql" else "THROW 'synthetic-atomic-batch-failure';"
    begin, commit = ("BEGIN;", "COMMIT;") if engine == "postgresql" else ("BEGIN TRANSACTION;", "COMMIT TRANSACTION;")
    body = begin+"\n"+batch.sql+"\n"+(failure+"\n" if inject_failure else "")+insert_receipt(engine,batch.receipt())+"\n"+commit
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("Wrapped SQL transaction exceeds encoded batch budget")
    return body


def ingest(client, engine, batches, *, on_receipt=None, interrupt_after=None):
    manifest = {"batch_id":"manifest","payload_sha256":manifest_sha256(batches),"seq_no":-1,"body_bytes":0}
    current, _ = client.query("SELECT "+FIELDS+" FROM bench_batch_receipt WHERE batch_id='manifest'")
    if current:
        if current != [manifest]:
            raise ValueError("Synthetic database belongs to a different batch manifest")
    else:
        client.sql(insert_receipt(engine,manifest))
        confirmed, _ = client.query("SELECT "+FIELDS+" FROM bench_batch_receipt WHERE batch_id='manifest'")
        if confirmed != [manifest]:
            raise ValueError("Batch manifest creation not confirmed")
    existing, _ = client.query("SELECT "+FIELDS+" FROM bench_batch_receipt WHERE batch_id!='manifest' ORDER BY seq_no")
    def confirm(batch):
        rows, _ = client.query("SELECT "+FIELDS+" FROM bench_batch_receipt WHERE batch_id='"+batch.batch_id+"'")
        return rows[0] if len(rows)==1 else None
    def send(batch):
        # sql() raises on ANY engine statement error; no next batch on failure.
        client.sql(transaction(engine,batch))
    return deliver(batches,existing=existing,send=send,confirm=confirm,on_receipt=on_receipt,interrupt_after=interrupt_after)
