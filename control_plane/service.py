"""Application boundary: transactions, permissions, missions and audit.

HTTP knows none of the persistence or lifecycle rules in this module.
"""

import time

from .auth import require_role, workspace_access
from .contracts import (
    Attempt, AuditEvent, Mission, Problem, Task, TRANSITIONS, WorkspaceReference,
    canonical, decode_json, fields, identifier, new_id, operation_id, sha256, text, timestamp,
)
from .storage import Store


class ControlPlane:
    def __init__(self, root, *, clock=time.time, settings=None, coordinator=None):
        self.store = Store(root, settings=settings)
        self.clock = clock
        from .execution import ExecutionManager
        try:
            self.execution = ExecutionManager(self, coordinator)
            self.execution.recover()
        except BaseException:
            self.store.close()
            raise

    def close(self):
        self.store.close()

    def _mission(self, con, principal, identity):
        require_role(principal, "admin")
        identifier(identity)
        row = con.execute("SELECT * FROM missions WHERE id=? AND owner=?", (identity, principal.identity)).fetchone()
        if row is None:
            raise Problem("not_found", 404)
        return row

    def _view(self, con, row):
        workspace = WorkspaceReference(row["workspace_id"], row["project"]).to_dict()
        result = Mission(row["id"], row["owner"], row["project"], workspace, row["title"], row["objective"],
                         row["state"], row["created_at"], decode_json(row["authorized_files"]),
                         {"input": "local_user", "execution": "simulation_only"}).to_dict()
        tasks = con.execute("SELECT * FROM tasks WHERE mission_id=?", (row["id"],)).fetchall()
        result["tasks"] = [Task(*(t[key] for key in ("id", "mission_id", "role", "capability", "worker_id", "state"))).to_dict() for t in tasks]
        result["plan"] = None if not tasks else decode_json(tasks[0]["plan"])
        attempts = con.execute("SELECT a.* FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE t.mission_id=? ORDER BY a.number", (row["id"],)).fetchall()
        result["attempts"] = [Attempt(*(a[key] for key in ("id", "task_id", "number", "worker_id", "state", "started_at", "deadline", "error_code"))).to_dict() for a in attempts]
        results = con.execute("SELECT r.id,r.attempt_id,r.version_id,r.provenance,v.file_id FROM results r JOIN versions v ON v.id=r.version_id WHERE v.mission_id=?", (row["id"],)).fetchall()
        result["results"] = [{**dict(r), "provenance": decode_json(r["provenance"])} for r in results]
        return result

    def _audit(self, con, principal, workspace_id, mission_id, event_type, details):
        allowed = {"state", "reason", "file_id", "version_id", "task_id", "attempt_id", "worker_id"}
        if set(details) - allowed:
            raise Problem("unsafe_audit_details", 500)
        con.execute("INSERT INTO events(id,mission_id,workspace_id,actor,at,type,details) VALUES (?,?,?,?,?,?,?)",
                    (new_id("e"), mission_id, workspace_id, principal.identity, timestamp(self.clock()), event_type, canonical(details)))

    def _transition(self, con, principal, row, target, *, reason=None):
        if target not in TRANSITIONS[row["state"]]:
            raise Problem("invalid_transition", 409)
        con.execute("UPDATE missions SET state=? WHERE id=?", (target, row["id"]))
        details = {"state": target}
        if reason is not None:
            details["reason"] = reason
        self._audit(con, principal, row["workspace_id"], row["id"], "mission_state", details)
        return con.execute("SELECT * FROM missions WHERE id=?", (row["id"],)).fetchone()

    def _operate(self, principal, operation, action, payload, effect, *, role="admin"):
        require_role(principal, role)
        operation_id(operation)
        request_hash = sha256(canonical({"action": action, "payload": payload}).encode())
        with self.store.transaction() as con:
            old = con.execute("SELECT * FROM operations WHERE actor=? AND id=?", (principal.identity, operation)).fetchone()
            if old is not None:
                if old["request_sha256"] != request_hash:
                    raise Problem("operation_conflict", 409)
                return decode_json(old["response"])
            response = effect(con)
            con.execute("INSERT INTO operations VALUES (?,?,?,?)", (principal.identity, operation, request_hash, canonical(response)))
            return response

    def workspaces(self, principal):
        require_role(principal, "admin")
        with self.store.transaction() as con:
            return [WorkspaceReference(r["id"], r["project"]).to_dict() for r in con.execute("SELECT * FROM workspaces WHERE owner=?", (principal.identity,))]

    def create_mission(self, principal, data):
        fields(data, ("operation_id", "title", "objective", "workspace_id"), ("authorized_files",))
        title, objective = text(data["title"], 160), text(data["objective"], 4000)
        identifier(data["workspace_id"])
        refs = data.get("authorized_files", [])
        if not isinstance(refs, list) or len(refs) > 32:
            raise Problem("invalid_file_references")
        for reference in refs:
            identifier(reference)
        if len(refs) != len(set(refs)):
            raise Problem("invalid_file_references")
        def effect(con):
            workspace = workspace_access(con, principal, data["workspace_id"])
            for reference in refs:
                if con.execute("SELECT 1 FROM versions v JOIN files f ON f.id=v.file_id WHERE v.id=? AND f.workspace_id=?", (reference, workspace["id"])).fetchone() is None:
                    raise Problem("not_found", 404)
            identity = new_id("m")
            con.execute("INSERT INTO missions VALUES (?,?,?,?,?,?,?,?,?)", (identity, principal.identity, workspace["project"], workspace["id"], title, objective, "draft", timestamp(self.clock()), canonical(refs)))
            self._audit(con, principal, workspace["id"], identity, "mission_created", {"state": "draft"})
            return self._view(con, self._mission(con, principal, identity))
        return self._operate(principal, data["operation_id"], "create_mission", data, effect)

    def get_mission(self, principal, identity):
        require_role(principal, "admin")
        self.execution.expire()
        with self.store.transaction() as con:
            return self._view(con, self._mission(con, principal, identity))

    def list_missions(self, principal):
        require_role(principal, "admin")
        self.execution.expire()
        with self.store.transaction() as con:
            rows = con.execute("SELECT * FROM missions WHERE owner=? ORDER BY created_at DESC,id DESC LIMIT 200", (principal.identity,)).fetchall()
            return [self._view(con, row) for row in rows]

    def events(self, principal, identity):
        with self.store.transaction() as con:
            self._mission(con, principal, identity)
            return [AuditEvent(r["id"], r["sequence"], r["mission_id"], r["workspace_id"], r["actor"], r["at"], r["type"], decode_json(r["details"])).to_dict()
                    for r in con.execute("SELECT * FROM events WHERE mission_id=? ORDER BY sequence", (identity,))]

    def dashboard(self, principal):
        require_role(principal, "admin")
        self.execution.expire()
        with self.store.transaction() as con:
            counts = {row["state"]: row["count"] for row in con.execute("SELECT state,COUNT(*) AS count FROM missions WHERE owner=? GROUP BY state", (principal.identity,))}
            active = con.execute("SELECT id,title,state FROM missions WHERE owner=? AND state IN ('running','cancel_requested') LIMIT 1", (principal.identity,)).fetchone()
        return {"mission_count": sum(counts.values()), "queued_tasks": counts.get("queued", 0),
                "completed_tasks": counts.get("completed", 0), "active_mission": None if active is None else dict(active),
                "nodes": self.execution.nodes(principal), "simulation_only": True}
