"""Local identities and enforced demonstration policies, not OS isolation.

Enrollment/rotation issue a credential to a private immutable file, offline CLI
only. API receives revocation requests but never returns a credential.
"""

import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3

from .contracts import Principal, Problem, canonical, decode_json, fields, identifier, new_id, sha256, timestamp
from .storage import private_directory, write_new


def worker_id(value):
    if value != "fake-cpu":
        identifier(value)
        if not value.startswith("n_"):
            raise Problem("invalid_worker_id")
    return value


def default_limits(settings):
    return {"max_concurrent_tasks": 1, "lease_seconds": settings.attempt_seconds,
            "max_output_bytes": min(settings.max_file_bytes, 65536)}


def policy(capabilities, limits, settings):
    if capabilities != ["demo.report.v1"]:
        raise Problem("unsupported_worker_capabilities")
    fields(limits, ("max_concurrent_tasks", "lease_seconds", "max_output_bytes"))
    if (any(type(value) is not int for value in limits.values()) or limits["max_concurrent_tasks"] != 1
            or not 1 <= limits["lease_seconds"] <= settings.attempt_seconds
            or not 1 <= limits["max_output_bytes"] <= min(65536, settings.max_file_bytes)):
        raise Problem("unsupported_worker_limits")
    return decode_json(canonical(capabilities)), decode_json(canonical(limits))


def public_worker(row):
    return {"schema": "pepeuch.control-plane/worker-identity/v1", "id": row["id"], "status": row["status"],
            "credential_epoch": row["credential_epoch"], "capabilities": decode_json(row["capabilities"]),
            "limits": decode_json(row["limits"]), "capacity": 1, "simulated": True,
            "hardware_verified": False, "gpu": None,
            "isolation": {"mode": "same_os_account", "enforced": False}}


def authenticate_worker(root, credential):
    """Read current registry per request; no cached worker authorization."""
    try:
        con = sqlite3.connect((Path(root) / "app/index.sqlite3").as_uri() + "?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA trusted_schema=OFF")
            digest = sha256(credential)
            for row in con.execute("SELECT id,status,credential_epoch,credential_sha256 FROM worker_identities WHERE credential_sha256=?", (digest,)):
                if row["status"] == "active" and hmac.compare_digest(row["credential_sha256"], digest):
                    return Principal(row["id"], "worker", row["credential_epoch"])
        finally:
            con.close()
    except sqlite3.Error:
        pass
    raise Problem("authentication_required", 401)


class WorkerRegistry:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def list(self, con=None, *, active_only=False):
        if con is None:
            with self.store.transaction() as transaction:
                return self.list(transaction, active_only=active_only)
        rows = con.execute("SELECT * FROM worker_identities ORDER BY created_at,id").fetchall()
        return [public_worker(row) for row in rows if not active_only or row["status"] == "active"]

    def authorize(self, con, principal):
        if not isinstance(principal, Principal) or principal.role != "worker":
            raise Problem("access_denied", 403)
        row = con.execute("SELECT * FROM worker_identities WHERE id=?", (principal.identity,)).fetchone()
        if (row is None or row["status"] != "active" or type(principal.credential_epoch) is not int
                or principal.credential_epoch != row["credential_epoch"]):
            raise Problem("worker_revoked_or_rotated", 403)
        policy(decode_json(row["capabilities"]), decode_json(row["limits"]), self.store.settings)
        return row

    def _audit(self, con, identity, reason):
        workspace = con.execute("SELECT id FROM workspaces ORDER BY id LIMIT 1").fetchone()[0]
        con.execute("INSERT INTO events(id,mission_id,workspace_id,actor,at,type,details) VALUES (?,?,?,?,?,?,?)",
                    (new_id("e"), None, workspace, "local-maintenance", timestamp(self.clock()), "worker_identity",
                     canonical({"worker_id": identity, "reason": reason})))

    def _credential(self, identity, epoch):
        directory = self.store.root / "secrets/workers"
        if not directory.exists():
            directory.mkdir(mode=0o700)
        private_directory(directory)
        raw = secrets.token_urlsafe(32).encode()
        path = directory / f"{identity}.{epoch}.token"
        write_new(path, raw + b"\n")
        for parent in (directory, self.store.root / "secrets"):
            fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return sha256(raw), str(path.relative_to(self.store.root))

    def enroll(self, *, capabilities=None, limits=None):
        capabilities, limits = policy(["demo.report.v1"] if capabilities is None else capabilities,
                                      default_limits(self.store.settings) if limits is None else limits, self.store.settings)
        identity = new_id("n")
        with self.store.transaction() as con:
            digest, path = self._credential(identity, 1)
            stamp = timestamp(self.clock())
            con.execute("INSERT INTO worker_identities VALUES (?,?,?,?,?,?,?,?)", (identity, "active", digest, 1, canonical(capabilities), canonical(limits), stamp, stamp))
            self._audit(con, identity, "explicit_enrollment")
            result = public_worker(con.execute("SELECT * FROM worker_identities WHERE id=?", (identity,)).fetchone())
        return {"worker": result, "credential_file": path}

    def rotate(self, identity, *, reactivate=False):
        worker_id(identity)
        with self.store.transaction() as con:
            row = con.execute("SELECT * FROM worker_identities WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise Problem("not_found", 404)
            if row["status"] == "revoked" and not reactivate:
                raise Problem("explicit_reactivation_required", 409)
            epoch = row["credential_epoch"] + 1
            digest, path = self._credential(identity, epoch)
            con.execute("UPDATE worker_identities SET credential_sha256=?,credential_epoch=?,status='active',updated_at=? WHERE id=?", (digest, epoch, timestamp(self.clock()), identity))
            self._audit(con, identity, "explicit_reactivation" if reactivate else "credential_rotation")
            result = public_worker(con.execute("SELECT * FROM worker_identities WHERE id=?", (identity,)).fetchone())
        return {"worker": result, "credential_file": path}

    def revoke(self, con, identity):
        worker_id(identity)
        row = con.execute("SELECT * FROM worker_identities WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise Problem("not_found", 404)
        if row["status"] != "revoked":
            con.execute("UPDATE worker_identities SET status='revoked',credential_epoch=credential_epoch+1,updated_at=? WHERE id=?", (timestamp(self.clock()), identity))
        return public_worker(con.execute("SELECT * FROM worker_identities WHERE id=?", (identity,)).fetchone())
