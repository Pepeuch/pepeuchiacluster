"""Whole-statement UTF-8 batch plans and explicit acknowledged-prefix resume.

No network/DB default. Callers must make each batch+receipt one transaction and
validate its response; a separately read receipt is required before advancing.
This module is used by the synthetic bench, not production Discovery imports.
"""

from dataclasses import dataclass
import hashlib
import json

from isolated_bench_workload import sql_batches


MAX_BODY_BYTES = 512*1024
RESERVED_BYTES = 2048  # Transaction and constant-size receipt statement.


@dataclass(frozen=True)
class Batch:
    batch_id: str
    seq_no: int
    sql: str
    payload_sha256: str
    body_bytes: int

    def receipt(self):
        return {"batch_id": self.batch_id, "seq_no": self.seq_no,
                "payload_sha256": self.payload_sha256, "body_bytes": self.body_bytes}


class DeliveryInterrupted(RuntimeError):
    pass


def plan(statements, *, max_statements=150):
    result = []
    for index, sql in enumerate(sql_batches(statements, max_bytes=MAX_BODY_BYTES-RESERVED_BYTES, max_statements=max_statements)):
        raw = sql.encode("utf-8")
        result.append(Batch(f"b{index:06d}", index, sql, hashlib.sha256(raw).hexdigest(), len(raw)))
    if not result:
        raise ValueError("Nonempty explicit SQL batch plan required")
    return tuple(result)


def manifest_sha256(batches):
    raw = json.dumps([b.receipt() for b in batches], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def deliver(batches, *, existing, send, confirm, on_receipt=None, interrupt_after=None):
    batches = tuple(batches)
    existing = list(existing)
    def matches(receipt, expected):
        return json.dumps(receipt,sort_keys=True,allow_nan=False) == json.dumps(expected,sort_keys=True,allow_nan=False)
    if len(existing) > len(batches) or any(not matches(receipt,batch.receipt()) for receipt, batch in zip(existing, batches)):
        raise ValueError("Only an exact acknowledged prefix can be resumed")
    if interrupt_after is not None and (type(interrupt_after) is not int or not 0 < interrupt_after < len(batches)-len(existing)):
        raise ValueError("Interruption must be between two pending batches")
    applied = 0
    for batch in batches[len(existing):]:
        send(batch)  # Must check EVERY engine response and commit atomically.
        receipt = confirm(batch)  # Independent read after commit, no inferred success.
        if not matches(receipt,batch.receipt()):
            raise ValueError("Batch acknowledgement missing or incompatible")
        applied += 1
        if on_receipt is not None:
            on_receipt(dict(receipt))
        if interrupt_after is not None and applied == interrupt_after:
            raise DeliveryInterrupted("Delivery interrupted between acknowledged SQL batches")
    return {"planned": len(batches), "already_acknowledged": len(existing), "applied": applied,
            "manifest_sha256": manifest_sha256(batches), "verified": True}
