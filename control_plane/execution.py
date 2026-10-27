"""Task/attempt manager. Coordinates declarations, leases and durable outcomes."""

from .auth import require_role
from .contracts import ExecutionResult, Principal, Problem, canonical, fields, identifier, new_id, sha256, timestamp
from .capabilities import CapabilityCoordinator, DEMO, SPECS


SYSTEM = Principal("local-system", "system")


class ExecutionManager:
    def __init__(self, service, coordinator=None):
        self.service = service
        self.coordinator = CapabilityCoordinator() if coordinator is None else coordinator

    def recover(self):
        with self.service.store.transaction() as con:
            self._fence(con, "backend_restart", expired_only=False)

    def _fence(self, con, reason, *, expired_only, worker_id=None):
        rows = con.execute("SELECT a.id,a.task_id,a.deadline,t.mission_id FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE a.state IN ('running','cancel_requested') AND (? IS NULL OR a.worker_id=?)", (worker_id, worker_id)).fetchall()
        for row in rows:
            if expired_only and row["deadline"] > self.service.clock():
                continue
            con.execute("UPDATE attempts SET state='interrupted',error_code=? WHERE id=?", (reason, row["id"]))
            con.execute("UPDATE tasks SET state='interrupted' WHERE id=?", (row["task_id"],))
            mission = con.execute("SELECT * FROM missions WHERE id=?", (row["mission_id"],)).fetchone()
            self.service._transition(con, SYSTEM, mission, "interrupted", reason=reason)

    def expire(self):
        with self.service.store.transaction() as con:
            self._fence(con, "attempt_expired", expired_only=True)

    def approve(self, principal, identity, data):
        fields(data, ("operation_id",))
        def effect(con):
            mission = self.service._mission(con, principal, identity)
            if mission["state"] != "draft":
                raise Problem("invalid_transition", 409)
            workers = tuple(self.service.registry.list(con, active_only=True))
            plan = self.coordinator.plan(self.service._view(con, mission), workers)
            fields(plan, ("schema", "simulated", "role", "capability", "worker_id", "instruction", "outputs"))
            capability = self.service._required_capability(con, identity)
            expected = SPECS[capability]
            if (plan["schema"] != "pepeuch.control-plane/plan/v1"
                    or plan["capability"] != capability
                    or any(plan[key] != value or type(plan[key]) is not type(value) for key, value in expected.items())
                    or plan["outputs"] != ["resultat.md"]
                    or not any(w["id"] == plan["worker_id"] and plan["capability"] in w["capabilities"] for w in workers)):
                raise Problem("invalid_plan", 409)
            mission = self.service._transition(con, principal, mission, "approved")
            con.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?)", (new_id("t"), identity, plan["role"], plan["capability"], plan["worker_id"], "queued", canonical(plan)))
            mission = self.service._transition(con, principal, mission, "queued")
            return self.service._view(con, mission)
        return self.service._operate(principal, data["operation_id"], "approve:" + identity, data, effect)

    def cancel(self, principal, identity, data):
        require_role(principal, "admin")
        fields(data, ("operation_id",))
        self.expire()
        def effect(con):
            mission = self.service._mission(con, principal, identity)
            if mission["state"] == "cancel_requested":
                return self.service._view(con, mission)
            target = "cancel_requested" if mission["state"] == "running" else "cancelled"
            mission = self.service._transition(con, principal, mission, target)
            con.execute("UPDATE tasks SET state=? WHERE mission_id=?", (target, identity))
            con.execute("UPDATE attempts SET state=? WHERE task_id IN (SELECT id FROM tasks WHERE mission_id=?) AND state='running'", (target, identity))
            return self.service._view(con, mission)
        return self.service._operate(principal, data["operation_id"], "cancel:" + identity, data, effect)

    def retry(self, principal, identity, data):
        require_role(principal, "admin")
        fields(data, ("operation_id",))
        self.expire()
        def effect(con):
            mission = self.service._mission(con, principal, identity)
            if mission["state"] not in {"failed", "interrupted"}:
                raise Problem("invalid_transition", 409)
            mission = self.service._transition(con, principal, mission, "queued", reason="explicit_retry")
            con.execute("UPDATE tasks SET state='queued' WHERE mission_id=?", (identity,))
            return self.service._view(con, mission)
        return self.service._operate(principal, data["operation_id"], "retry:" + identity, data, effect)

    def claim(self, principal, data):
        require_role(principal, "worker")
        fields(data, ("operation_id",))
        def effect(con):
            worker = self.service.registry.authorize(con, principal)
            self._fence(con, "attempt_expired", expired_only=True)
            if con.execute("SELECT 1 FROM attempts WHERE worker_id=? AND state IN ('running','cancel_requested')", (principal.identity,)).fetchone():
                return {"request": None}
            task = con.execute("SELECT t.* FROM tasks t JOIN missions m ON m.id=t.mission_id WHERE t.state='queued' AND m.state='queued' AND t.worker_id=? ORDER BY m.created_at,m.id LIMIT 1", (principal.identity,)).fetchone()
            if task is None:
                return {"request": None}
            mission = con.execute("SELECT * FROM missions WHERE id=?", (task["mission_id"],)).fetchone()
            current = con.execute("SELECT v.id FROM versions v JOIN files f ON f.id=v.file_id WHERE f.workspace_id=? AND f.name='resultat.md' ORDER BY v.number DESC LIMIT 1", (mission["workspace_id"],)).fetchone()
            expected = None if current is None else current["id"]
            identity, generation = new_id("a"), new_id("g")
            number = con.execute("SELECT COALESCE(MAX(number),0)+1 FROM attempts WHERE task_id=?", (task["id"],)).fetchone()[0]
            now = self.service.clock()
            from .contracts import decode_json
            limits = decode_json(worker["limits"])
            started, deadline = timestamp(now), now + min(self.service.store.settings.attempt_seconds, limits["lease_seconds"])
            con.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)", (identity, task["id"], number, principal.identity, "running", generation, started, deadline, expected, None, None))
            con.execute("INSERT INTO attempt_worker_epochs VALUES (?,?)", (identity, principal.credential_epoch))
            con.execute("UPDATE tasks SET state='running' WHERE id=?", (task["id"],))
            self.service._transition(con, principal, mission, "running")
            self.service._audit(con, principal, mission["workspace_id"], mission["id"], "attempt_started", {"attempt_id": identity, "task_id": task["id"], "worker_id": principal.identity})
            task_view = {"schema": "pepeuch.control-plane/task/v1", **dict(task), "state": "running", "simulated": SPECS[task["capability"]]["simulated"]}
            task_view.pop("plan")
            return {"request": {"schema": "pepeuch.control-plane/execution-request/v1", "attempt_id": identity,
                                "generation": generation, "task": task_view,
                                "mission": {key: mission[key] for key in ("id", "title", "objective")},
                                "authorized_files": self.service._view(con, mission)["authorized_files"],
                                "started_at": started, "deadline": deadline, "expected_version": expected}}
        return self.service._operate(principal, data["operation_id"], "claim", data, effect, role="worker")

    def finish(self, principal, identity, result):
        require_role(principal, "worker")
        result = ExecutionResult.from_dict(result.to_dict())
        identifier(identity)
        if result.attempt_id != identity:
            raise Problem("attempt_mismatch", 409)
        self.expire()
        content_hash = sha256(canonical(result.to_dict()).encode())
        with self.service.store.transaction() as con:
            self.service.registry.authorize(con, principal)
            attempt = con.execute("SELECT a.*,t.mission_id,t.capability FROM attempts a JOIN tasks t ON t.id=a.task_id WHERE a.id=? AND a.worker_id=?", (identity, principal.identity)).fetchone()
            if attempt is None:
                raise Problem("not_found", 404)
            if attempt["generation"] != result.generation:
                raise Problem("stale_attempt", 409)
            epoch = con.execute("SELECT credential_epoch FROM attempt_worker_epochs WHERE attempt_id=?", (identity,)).fetchone()
            if epoch is None or epoch[0] != principal.credential_epoch:
                raise Problem("stale_attempt", 409)
            if attempt["result_sha256"] is not None:
                if attempt["result_sha256"] != content_hash:
                    raise Problem("result_conflict", 409)
                return {"accepted": True, "duplicate": True, "mission_id": attempt["mission_id"]}
            mission = con.execute("SELECT * FROM missions WHERE id=?", (attempt["mission_id"],)).fetchone()
            if attempt["state"] not in {"running", "cancel_requested"}:
                raise Problem("stale_attempt", 409)
            if mission["state"] == "cancel_requested":
                if result.status != "cancelled" or result.outputs or result.error_code is not None:
                    raise Problem("cancellation_pending", 409)
            elif result.status == "cancelled":
                raise Problem("invalid_transition", 409)
            if result.status == "completed":
                if result.error_code is not None or len(result.outputs) != 1:
                    raise Problem("invalid_outputs")
                publisher = getattr(self.service, "workspace", None)
                if publisher is None:
                    raise Problem("workspace_not_ready", 503)
                publisher.publish_result(con, principal, mission, attempt, result.outputs[0])
            else:
                errors = ({"failed": {"simulated_failure"}, "interrupted": {"simulated_interruption"}, "cancelled": {None}}
                          if attempt["capability"] == DEMO else
                          {"failed": {"cpu_execution_failed"}, "interrupted": {"cpu_interrupted", "cpu_deadline_exceeded"}, "cancelled": {None}})
                if result.outputs or result.error_code not in errors[result.status]:
                    raise Problem("invalid_failure_result")
            if self.service.clock() >= attempt["deadline"]:
                raise Problem("stale_attempt", 409)
            con.execute("UPDATE attempts SET state=?,result_sha256=?,error_code=? WHERE id=?", (result.status, content_hash, result.error_code, identity))
            con.execute("UPDATE tasks SET state=? WHERE id=?", (result.status, attempt["task_id"]))
            self.service._transition(con, principal, mission, result.status)
            return {"accepted": True, "duplicate": False, "mission_id": mission["id"]}

    def nodes(self, principal):
        require_role(principal, "admin")
        self.expire()
        with self.service.store.transaction() as con:
            result = []
            for worker in self.service.registry.list(con):
                active = con.execute("SELECT COUNT(*) FROM attempts WHERE worker_id=? AND state IN ('running','cancel_requested')", (worker["id"],)).fetchone()[0]
                verified = con.execute("SELECT COUNT(*) FROM results r JOIN attempts a ON a.id=r.attempt_id WHERE a.worker_id=?", (worker["id"],)).fetchone()[0]
                entry = {**worker, "state": "revoked" if worker["status"] == "revoked" else ("simulated_busy" if worker["simulated"] else "cpu_busy") if active else "manual_idle",
                         "verified_simulated_executions": verified if worker["simulated"] else 0, "online_verified": False}
                if not worker["simulated"]:
                    entry["accepted_cpu_results"] = verified
                result.append(entry)
        return result

    def state(self, principal, identity):
        require_role(principal, "worker")
        identifier(identity)
        self.expire()
        with self.service.store.transaction() as con:
            self.service.registry.authorize(con, principal)
            row = con.execute("SELECT state,deadline FROM attempts WHERE id=? AND worker_id=?", (identity, principal.identity)).fetchone()
            if row is None:
                raise Problem("not_found", 404)
            epoch = con.execute("SELECT credential_epoch FROM attempt_worker_epochs WHERE attempt_id=?", (identity,)).fetchone()
            if epoch is None or epoch[0] != principal.credential_epoch:
                raise Problem("stale_attempt", 409)
            return {"schema": "pepeuch.control-plane/attempt-state/v1", **dict(row)}
