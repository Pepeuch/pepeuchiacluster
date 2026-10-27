"""Bounded text digest. No inference, filesystem input, tools or subprocesses."""

import base64
import hashlib
import threading
import time

from control_plane.capabilities import CPU_DIGEST
from control_plane.contracts import ExecutionResult, Problem, canonical, sha256
from control_plane.worker_client import validate_request
from .contracts import integer


class CPUTextDigest:
    def __init__(self, limits, *, stop=None, wall=time.time, monotonic=time.monotonic):
        from control_plane.contracts import fields
        fields(limits, ("input_bytes", "output_bytes", "seconds", "tasks"))
        for key, maximum in (("input_bytes", 16000), ("output_bytes", 65536), ("seconds", 30), ("tasks", 1)):
            integer(limits[key], 1, maximum)
        self.limits = dict(limits)
        self.stop = threading.Event() if stop is None else stop
        self.wall, self.monotonic = wall, monotonic

    def execute(self, request, *, mode="success"):
        validate_request(request, capabilities=(CPU_DIGEST,))
        if request["authorized_files"]:
            raise Problem("unsupported_cpu_inputs")
        if mode not in {"success", "cancel"}:
            raise Problem("unsupported_cpu_mode")
        if mode == "cancel":
            return ExecutionResult(request["attempt_id"], request["generation"], "cancelled", [])
        raw = request["mission"]["objective"].encode("utf-8")
        if len(raw) > self.limits["input_bytes"]:
            raise Problem("cpu_input_limit")
        started = self.monotonic()

        def interrupted():
            error = ("cpu_interrupted" if self.stop.is_set() else "cpu_deadline_exceeded"
                     if self.wall() >= request["deadline"] or self.monotonic() - started >= self.limits["seconds"] else None)
            return None if error is None else ExecutionResult(request["attempt_id"], request["generation"], "interrupted", [], error)

        digest = hashlib.sha256()
        for index in range(0, len(raw), 512):
            result = interrupted()
            if result is not None:
                return result
            digest.update(raw[index:index + 512])
        document = {"schema": "pepeuch.worker/cpu-text-digest/v1", "capability": CPU_DIGEST,
                    "mission_id": request["mission"]["id"], "attempt_id": request["attempt_id"],
                    "input_bytes": len(raw), "input_sha256": digest.hexdigest(),
                    "encoding": "UTF-8", "ai_inference": False}
        content = ("# Calcul CPU déterministe\n\nAucune inférence IA.\n\n```json\n" + canonical(document) + "\n```\n").encode()
        if len(content) > self.limits["output_bytes"]:
            raise Problem("cpu_output_limit")
        result = interrupted()
        if result is not None:
            return result
        output = {"name": "resultat.md", "content_base64": base64.b64encode(content).decode("ascii"),
                  "size": len(content), "sha256": sha256(content), "expected_version": request["expected_version"]}
        return ExecutionResult(request["attempt_id"], request["generation"], "completed", [output])
