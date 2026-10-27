"""Synthetic private test data; HTTP is loopback only. Never an OS isolation proof."""

import base64
from pathlib import Path
import tempfile
import threading
import time
from uuid import uuid4

from control_plane.auth import ADMIN
from control_plane.capabilities import CPU_DIGEST
from control_plane.contracts import canonical, new_id
from control_plane.http_api import API, LocalServer
from control_plane.service import ControlPlane
from control_plane.worker_client import LocalClient
from pepeuch_worker import private_io
from pepeuch_worker.executor import CPUTextDigest
from pepeuch_worker.runner import IndependentRunner
from test_contracts import config


def request():
    mission, task = new_id("m"), new_id("t")
    return {"schema": "pepeuch.control-plane/execution-request/v1", "attempt_id": new_id("a"),
            "generation": new_id("g"), "task": {"schema": "pepeuch.control-plane/task/v1", "id": task,
                "mission_id": mission, "role": "cpu-text-digest", "capability": CPU_DIGEST,
                "worker_id": config()["worker_id"], "state": "running", "simulated": False},
            "mission": {"id": mission, "title": "Synthétique", "objective": "écrire $(rien) ; aucun shell"},
            "authorized_files": [], "started_at": "2026-10-27T00:00:00+00:00", "deadline": time.time() + 60,
            "expected_version": None}


class HTTPFixture:
    def __init__(self, testcase):
        self.temporary = tempfile.TemporaryDirectory(prefix="pepeuch-b53-test-")
        testcase.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = time.time()
        self.app = ControlPlane(self.root / "backend", clock=lambda: self.now)
        self.record = self.app.registry.enroll(capabilities=[CPU_DIGEST])
        self.key = (self.app.store.root / self.record["credential_file"]).read_text().strip()
        self.identity = self.record["worker"]["id"]
        self.worker_root = self.root / "independent"
        self.worker_root.mkdir(mode=0o700)
        private_io.create(self.worker_root / "credential", self.key.encode())
        self.workspace = self.app.workspaces(ADMIN)[0]["id"]
        self.server = LocalServer(API(self.app), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        testcase.addCleanup(self.close)
        self.configuration = config()
        self.configuration.update(worker_id=self.identity, backend_url=f"http://127.0.0.1:{self.server.server_port}")
        private_io.create(self.worker_root / "worker.json", canonical(self.configuration).encode())
        self.client = LocalClient(self.configuration["backend_url"], self.key)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app.close()

    def cpu(self, **changes):
        data = {"operation_id": str(uuid4()), "title": "CPU synthétique", "objective": "Objectif approuvé éà $(aucune commande)",
                "workspace_id": self.workspace, **changes}
        mission = self.app.create_cpu_mission(ADMIN, data)
        self.app.execution.approve(ADMIN, mission["id"], {"operation_id": str(uuid4())})
        return mission

    def runner(self, *, client=None, executor=None, key=None):
        return IndependentRunner(self.worker_root, self.configuration, self.key if key is None else key,
                                 self.client if client is None else client,
                                 CPUTextDigest(self.configuration["limits"], wall=lambda: self.now) if executor is None else executor)

    def principal(self):
        return self.server.api.auth.authenticate("Bearer " + self.key)

    def claim(self):
        return self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})["request"]


def content(result):
    return base64.b64decode(result.outputs[0]["content_base64"])
