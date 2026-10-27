"""Closed, typed execution capabilities. No model, tool or runtime discovery."""

DEMO = "demo.report.v1"
CPU_DIGEST = "cpu.text.sha256.v1"
SPECS = {
    DEMO: {"role": "demo-report", "instruction": "produce_deterministic_report", "simulated": True},
    CPU_DIGEST: {"role": "cpu-text-digest", "instruction": "hash_authorized_objective_utf8", "simulated": False},
}
