"""Immutable local objects + transactional logical versions, not host paths."""

import base64
import binascii
import os
import re

from .auth import require_role, workspace_access
from .contracts import Problem, canonical, decode_json, fields, identifier, new_id, sha256, timestamp
from .storage import private_directory, read_private, write_new


def file_name(name):
    reserved = {"CON", "PRN", "AUX", "NUL", *("COM" + str(n) for n in range(1, 10)), *("LPT" + str(n) for n in range(1, 10))}
    if (not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", name) is None
            or name.endswith(".") or name.split(".")[0].upper() in reserved):
        raise Problem("unsafe_file_name")
    return name


def output_data(data, limit):
    fields(data, ("name", "content_base64", "size", "sha256", "expected_version"))
    name = file_name(data["name"])
    if type(data["size"]) is not int or data["size"] < 0:
        raise Problem("invalid_file_size")
    if data["size"] > limit:
        raise Problem("file_too_large", 413)
    if data["expected_version"] is not None:
        identifier(data["expected_version"])
    if not isinstance(data["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", data["sha256"]) is None:
        raise Problem("invalid_file_digest")
    encoded = data["content_base64"]
    if not isinstance(encoded, str) or len(encoded) > ((limit + 2) // 3) * 4:
        raise Problem("file_too_large", 413)
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise Problem("invalid_file_encoding") from None
    if len(raw) != data["size"] or sha256(raw) != data["sha256"]:
        raise Problem("file_integrity_mismatch")
    return name, raw


class WorkspaceManager:
    def __init__(self, service):
        self.service = service
        self.root = service.store.root

    def _object(self, raw):
        staging = private_directory(self.root / "staging")
        objects = private_directory(self.root / "objects")
        temporary = staging / new_id("p")
        identity = sha256(raw)
        target = objects / identity
        try:
            write_new(temporary, raw)
            staged = read_private(temporary, self.service.store.settings.max_file_bytes)
            if staged != raw or sha256(staged) != identity:
                raise Problem("incomplete_staging", 500)
            if os.path.lexists(target):
                if read_private(target, self.service.store.settings.max_file_bytes) != raw:
                    raise Problem("object_corrupted", 500)
            else:
                os.replace(temporary, target)
                fd = os.open(objects, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            if read_private(target, self.service.store.settings.max_file_bytes) != raw:
                raise Problem("object_corrupted", 500)
        finally:
            temporary.unlink(missing_ok=True)
        return identity

    def _publish(self, con, principal, workspace_id, name, raw, expected, *, mission_id=None, attempt_id=None):
        file = con.execute("SELECT * FROM files WHERE workspace_id=? AND name=?", (workspace_id, name)).fetchone()
        previous = None if file is None else con.execute("SELECT * FROM versions WHERE file_id=? ORDER BY number DESC LIMIT 1", (file["id"],)).fetchone()
        if expected != (None if previous is None else previous["id"]):
            raise Problem("version_conflict", 409)
        used = con.execute("SELECT COALESCE(SUM(v.size),0) FROM versions v JOIN files f ON f.id=v.file_id WHERE f.workspace_id=?", (workspace_id,)).fetchone()[0]
        if used + len(raw) > self.service.store.settings.quota_bytes:
            raise Problem("workspace_quota_exceeded", 413)
        if file is None and con.execute("SELECT COUNT(*) FROM files WHERE workspace_id=?", (workspace_id,)).fetchone()[0] >= 100:
            raise Problem("file_count_limit", 413)
        if previous is not None and previous["number"] >= 100:
            raise Problem("version_count_limit", 413)
        identity = self._object(raw)
        file_id = new_id("f") if file is None else file["id"]
        if file is None:
            con.execute("INSERT INTO files VALUES (?,?,?)", (file_id, workspace_id, name))
        version_id = new_id("v")
        con.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?)", (version_id, file_id, 1 if previous is None else previous["number"] + 1,
                    len(raw), identity, timestamp(self.service.clock()), mission_id, attempt_id))
        self.service._audit(con, principal, workspace_id, mission_id, "file_published", {"file_id": file_id, "version_id": version_id})
        return {"file_id": file_id, "version_id": version_id, "sha256": identity, "size": len(raw)}

    def upload(self, principal, workspace_id, data):
        require_role(principal, "admin")
        fields(data, ("operation_id", "name", "content_base64", "size", "sha256", "expected_version"))
        file_data = {key: value for key, value in data.items() if key != "operation_id"}
        name, raw = output_data(file_data, self.service.store.settings.max_file_bytes)
        def effect(con):
            workspace_access(con, principal, workspace_id)
            return self._publish(con, principal, workspace_id, name, raw, data["expected_version"])
        return self.service._operate(principal, data["operation_id"], "upload:" + workspace_id, data, effect)

    def publish_result(self, con, principal, mission, attempt, output):
        require_role(principal, "worker")
        if principal.identity != attempt["worker_id"]:
            raise Problem("access_denied", 403)
        worker = self.service.registry.authorize(con, principal)
        limit = decode_json(worker["limits"])["max_output_bytes"]
        name, raw = output_data(output, min(65536, self.service.store.settings.max_file_bytes, limit))
        if name != "resultat.md" or output["expected_version"] != attempt["expected_version"]:
            raise Problem("result_contract_mismatch", 409)
        published = self._publish(con, principal, mission["workspace_id"], name, raw, attempt["expected_version"],
                                  mission_id=mission["id"], attempt_id=attempt["id"])
        from .capabilities import DEMO, CPU_DIGEST
        provenance = ('{"simulated":true,"capability":"demo.report.v1","verification":"deterministic_demo_only"}'
                      if attempt["capability"] == DEMO else canonical({"simulated": False, "capability": CPU_DIGEST,
                          "verification": "worker_reported_cpu_digest", "ai_inference": False, "os_isolation": "NOT VERIFIED"}))
        con.execute("INSERT INTO results VALUES (?,?,?,?)", (new_id("r"), attempt["id"], published["version_id"], provenance))
        return published

    def list_files(self, principal, workspace_id):
        with self.service.store.transaction() as con:
            workspace_access(con, principal, workspace_id)
            files = []
            for file in con.execute("SELECT * FROM files WHERE workspace_id=? ORDER BY name", (workspace_id,)).fetchall():
                versions = [dict(row) for row in con.execute("SELECT * FROM versions WHERE file_id=? ORDER BY number DESC", (file["id"],))]
                files.append({"id": file["id"], "name": file["name"], "current_version": versions[0]["id"], "versions": versions})
            used = sum(v["size"] for f in files for v in f["versions"])
            return {"schema": "pepeuch.control-plane/workspace-files/v1", "workspace_id": workspace_id,
                    "files": files, "used_bytes": used, "quota_bytes": self.service.store.settings.quota_bytes,
                    "max_file_bytes": self.service.store.settings.max_file_bytes}

    def download(self, principal, workspace_id, file_id, version_id=None):
        identifier(file_id)
        if version_id is not None:
            identifier(version_id)
        with self.service.store.transaction() as con:
            workspace_access(con, principal, workspace_id)
            file = con.execute("SELECT * FROM files WHERE id=? AND workspace_id=?", (file_id, workspace_id)).fetchone()
            if file is None:
                raise Problem("not_found", 404)
            version = con.execute("SELECT * FROM versions WHERE file_id=? AND (? IS NULL OR id=?) ORDER BY number DESC LIMIT 1", (file_id, version_id, version_id)).fetchone()
            if version is None:
                raise Problem("not_found", 404)
            if re.fullmatch(r"[0-9a-f]{64}", version["sha256"]) is None:
                raise Problem("object_corrupted", 500)
            private_directory(self.root / "objects")
            raw = read_private(self.root / "objects" / version["sha256"], self.service.store.settings.max_file_bytes)
            if len(raw) != version["size"] or sha256(raw) != version["sha256"]:
                raise Problem("object_corrupted", 500)
            return raw, file["name"], version["sha256"]
