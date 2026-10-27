"""Closed, typed execution capabilities. No model, tool or runtime discovery."""

DEMO = "demo.report.v1"
CPU_DIGEST = "cpu.text.sha256.v1"
SPECS = {
    DEMO: {"role": "demo-report", "instruction": "produce_deterministic_report", "simulated": True},
    CPU_DIGEST: {"role": "cpu-text-digest", "instruction": "hash_authorized_objective_utf8", "simulated": False},
}


class CapabilityCoordinator:
    """Fixed routing rules, not an intelligent coordinator or a scheduler."""

    def plan(self, mission, workers):
        from .contracts import Problem
        from .demo import FakeCoordinator
        capability = mission.get("required_capability", DEMO)
        if capability == DEMO:
            return FakeCoordinator().plan(mission, workers)
        if capability != CPU_DIGEST or mission["authorized_files"]:
            raise Problem("unsupported_cpu_inputs", 409)
        selected = next((w for w in workers if capability in w["capabilities"]), None)
        if selected is None:
            raise Problem("no_declared_capability", 409)
        return {"schema": "pepeuch.control-plane/plan/v1", **SPECS[capability],
                "capability": capability, "worker_id": selected["id"], "outputs": ["resultat.md"]}
