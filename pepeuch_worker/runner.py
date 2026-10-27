"""One manual task; restart replays publication or interrupts, never recomputes."""

from uuid import uuid4

from control_plane.capabilities import CPU_DIGEST
from control_plane.contracts import ExecutionResult, Problem, fields, operation_id, sha256
from control_plane.worker_client import validate_request
from . import private_io


JOURNAL_SCHEMA = "pepeuch.worker/run/v1"


class IndependentRunner:
    def __init__(self, root, configuration, credential, client, executor):
        self.root, self.config = root, configuration
        self.client, self.executor = client, executor
        self.fingerprint = sha256(credential.encode("ascii"))

    def _request(self, request):
        validate_request(request, capabilities=(CPU_DIGEST,))
        if request["task"]["worker_id"] != self.config["worker_id"] or request["authorized_files"]:
            raise Problem("worker_scope_mismatch")

    def _state(self, request):
        reply = self.client.call("GET", "/api/v1/execution/" + request["attempt_id"] + "/state")
        fields(reply, ("schema", "state", "deadline"))
        if (reply["schema"] != "pepeuch.control-plane/attempt-state/v1" or type(reply["deadline"]) not in (int, float)
                or reply["deadline"] != request["deadline"] or not isinstance(reply["state"], str)
                or reply["state"] not in {"running", "cancel_requested", "completed", "failed", "interrupted", "cancelled"}):
            raise Problem("invalid_worker_response")
        return reply["state"]

    def run_once(self, *, recover=False):
        with private_io.locked(self.root):
            journal = private_io.load(self.root)
            pending = journal is not None
            if pending:
                fields(journal, ("schema", "worker_id", "backend_url", "credential_sha256", "claim_id", "request", "result", "done"))
                if (journal["schema"] != JOURNAL_SCHEMA or journal["worker_id"] != self.config["worker_id"]
                        or type(journal["done"]) is not bool):
                    raise Problem("worker_journal_identity_mismatch")
                operation_id(journal["claim_id"])
                pending = not journal["done"]
                if pending and (journal["credential_sha256"] != self.fingerprint or journal["backend_url"] != self.config["backend_url"]):
                    raise Problem("worker_journal_identity_mismatch")
            if pending and not recover:
                raise Problem("explicit_worker_recovery_required", 409)
            if not pending:
                if recover:
                    return "nothing_to_recover"
                journal = {"schema": JOURNAL_SCHEMA, "worker_id": self.config["worker_id"],
                           "backend_url": self.config["backend_url"],
                           "credential_sha256": self.fingerprint, "claim_id": str(uuid4()),
                           "request": None, "result": None, "done": False}
                private_io.save(self.root, journal)
            if journal["request"] is None:
                response = self.client.call("POST", "/api/v1/execution/claim", {"operation_id": journal["claim_id"]})
                fields(response, ("request",))
                journal["request"] = response["request"]
                if journal["request"] is None:
                    journal["done"] = True
                    private_io.save(self.root, journal)
                    return "idle"
                self._request(journal["request"])
                private_io.save(self.root, journal)
            request = journal["request"]
            self._request(request)
            state = self._state(request)
            if state not in {"running", "cancel_requested"}:
                # Terminal attempt: no result may be manufactured or recomputed.
                journal["done"] = True
                private_io.save(self.root, journal)
                return state
            if state == "cancel_requested":
                result = ExecutionResult(request["attempt_id"], request["generation"], "cancelled", [])
            elif journal["result"] is not None:
                result = ExecutionResult.from_dict(journal["result"])
                if result.attempt_id != request["attempt_id"] or result.generation != request["generation"]:
                    raise Problem("worker_journal_attempt_mismatch")
            elif pending:
                result = ExecutionResult(request["attempt_id"], request["generation"], "interrupted", [], "cpu_interrupted")
            else:
                try:
                    result = self.executor.execute(request)
                except KeyboardInterrupt:
                    result = ExecutionResult(request["attempt_id"], request["generation"], "interrupted", [], "cpu_interrupted")
                except Problem:
                    result = ExecutionResult(request["attempt_id"], request["generation"], "failed", [], "cpu_execution_failed")
            journal["result"] = result.to_dict()
            private_io.save(self.root, journal)
            # Observe cancellation immediately before publication as well.
            state = self._state(request)
            if state not in {"running", "cancel_requested"}:
                journal["done"] = True
                private_io.save(self.root, journal)
                return state
            if state == "cancel_requested" and result.status != "cancelled":
                result = ExecutionResult(request["attempt_id"], request["generation"], "cancelled", [])
                journal["result"] = result.to_dict()
                private_io.save(self.root, journal)
            acknowledgement = self.client.call("POST", "/api/v1/execution/" + request["attempt_id"] + "/finish", result.to_dict())
            fields(acknowledgement, ("accepted", "duplicate", "mission_id"))
            if (acknowledgement["accepted"] is not True or type(acknowledgement["duplicate"]) is not bool
                    or acknowledgement["mission_id"] != request["mission"]["id"]):
                raise Problem("invalid_worker_response")
            journal["done"] = True
            private_io.save(self.root, journal)
            return result.status
