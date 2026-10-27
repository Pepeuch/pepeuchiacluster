"""Replaceable simulation components. No AI, GPU, shell, tools or networking."""

import base64

from .contracts import ExecutionResult, Problem, fields, sha256, text


CAPABILITY = "demo.report.v1"
WORKERS = ({"id": "fake-cpu", "simulated": True, "capabilities": [CAPABILITY], "capacity": 1,
            "hardware_verified": False, "gpu": None},)


class FakeCoordinator:
    def plan(self, mission, workers):
        selected = next((w for w in workers if CAPABILITY in w["capabilities"]), None)
        if selected is None:
            raise Problem("no_declared_capability", 409)
        return {"schema": "pepeuch.control-plane/plan/v1", "simulated": True,
                "role": "demo-report", "capability": CAPABILITY, "worker_id": selected["id"],
                "instruction": "produce_deterministic_report", "outputs": ["resultat.md"]}


class FakeWorker:
    def execute(self, request, *, mode="success"):
        fields(request, ("schema", "attempt_id", "generation", "task", "mission", "authorized_files",
                         "started_at", "deadline", "expected_version"))
        if (request["schema"] != "pepeuch.control-plane/execution-request/v1"
                or request["task"]["capability"] != CAPABILITY):
            raise Problem("unsupported_execution_contract")
        if mode in {"fail", "interrupt", "cancel"}:
            state, error = {"fail": ("failed", "simulated_failure"),
                            "interrupt": ("interrupted", "simulated_interruption"),
                            "cancel": ("cancelled", None)}[mode]
            return ExecutionResult(request["attempt_id"], request["generation"], state, [], error)
        if mode != "success":
            raise Problem("unsupported_demo_mode")
        mission = request["mission"]
        title = text(mission["title"], 160)
        objective = text(mission["objective"], 4000)
        content = (f"# {title}\n\nSIMULATION — aucun agent IA ni aucune inférence.\n\n"
                   f"Mission : {mission['id']}\nTentative : {request['attempt_id']}\n"
                   f"Date d'exécution : {request['started_at']}\n"
                   f"Tâche : {request['task']['id']}\nRôle : {request['task']['role']}\n\n"
                   f"Résumé déterministe de la tâche reçue :\n{objective}\n").encode("utf-8")
        output = {"name": "resultat.md", "content_base64": base64.b64encode(content).decode("ascii"),
                  "size": len(content), "sha256": sha256(content), "expected_version": request["expected_version"]}
        return ExecutionResult(request["attempt_id"], request["generation"], "completed", [output])
