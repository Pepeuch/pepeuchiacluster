"""Explicit local worker runner. No direct SQLite/filesystem business access."""

from http.client import HTTPConnection, HTTPException
from datetime import datetime
import re
from urllib.parse import urlsplit
from uuid import uuid4

from .contracts import Executor, Problem, canonical, decode_json, fields, identifier, text
from .demo import FakeWorker
from .http_io import DeadlineSocket


class LocalConnection(HTTPConnection):
    def connect(self):
        super().connect()
        self.sock = DeadlineSocket(self.sock)


class LocalClient:
    def __init__(self, base_url, credential):
        try:
            parsed = urlsplit(base_url)
            valid = (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port is not None
                     and parsed.username is None and parsed.password is None and parsed.path in ("", "/")
                     and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise Problem("worker_loopback_only")
        self.base_url = base_url.rstrip("/")
        self.port = parsed.port
        self.credential = credential

    def call(self, method, path, data=None):
        if (method not in {"GET", "POST"} or re.fullmatch(r"/api/v1/execution/(?:claim|a_[0-9a-f]{32}/(?:state|finish))", path) is None):
            raise Problem("invalid_worker_route")
        raw = None if data is None else canonical(data).encode()
        connection = LocalConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=raw, headers={"Authorization": "Bearer " + self.credential, "Content-Type": "application/json"})
            with connection.getresponse() as response:
                if response.status != 200:
                    raise Problem("worker_request_refused", 409)
                lengths = response.headers.get_all("Content-Length", [])
                types = response.headers.get_all("Content-Type", [])
                if (len(lengths) != 1 or re.fullmatch(r"[0-9]{1,6}", lengths[0]) is None
                        or int(lengths[0]) > 131072 or response.headers.get_all("Transfer-Encoding")
                        or response.headers.get_all("Content-Encoding")
                        or types != ["application/json; charset=utf-8"]):
                    raise Problem("invalid_worker_response")
                raw = response.read(131073)
                if len(raw) != int(lengths[0]):
                    raise Problem("invalid_worker_response")
                data = decode_json(raw)
                if not isinstance(data, dict):
                    raise Problem("invalid_worker_response")
                return data
        except (HTTPException, OSError, ValueError):
            raise Problem("backend_unavailable", 503) from None
        finally:
            connection.close()


class WorkerRunner:
    def __init__(self, client, executor: Executor | None = None):
        self.client = client
        self.executor = FakeWorker() if executor is None else executor

    def run_once(self, *, mode="success", before_execute=None):
        response = self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})
        fields(response, ("request",))
        request = response["request"]
        if request is None:
            return "idle"
        validate_request(request)
        if mode == "hold":
            return "held"
        if before_execute is not None:
            before_execute(request)
        state_reply = self.client.call("GET", "/api/v1/execution/" + request["attempt_id"] + "/state")
        fields(state_reply, ("schema", "state", "deadline"))
        state = state_reply["state"]
        if (state_reply["schema"] != "pepeuch.control-plane/attempt-state/v1"
                or not isinstance(state, str) or state not in {"running", "cancel_requested", "completed", "failed", "interrupted", "cancelled"}
                or type(state_reply["deadline"]) not in (int, float) or state_reply["deadline"] != request["deadline"]):
            raise Problem("invalid_worker_response")
        if state not in {"running", "cancel_requested"}:
            return state
        result = self.executor.execute(request, mode="cancel" if state == "cancel_requested" else mode)
        acknowledgement = self.client.call("POST", "/api/v1/execution/" + request["attempt_id"] + "/finish", result.to_dict())
        fields(acknowledgement, ("accepted", "duplicate", "mission_id"))
        if acknowledgement["accepted"] is not True or type(acknowledgement["duplicate"]) is not bool or acknowledgement["mission_id"] != request["mission"]["id"]:
            raise Problem("invalid_worker_response")
        return result.status


def validate_request(request):
    fields(request, ("schema", "attempt_id", "generation", "task", "mission", "authorized_files", "started_at", "deadline", "expected_version"))
    task, mission = request["task"], request["mission"]
    fields(task, ("schema", "id", "mission_id", "role", "capability", "worker_id", "state", "simulated"))
    fields(mission, ("id", "title", "objective"))
    for value in (request["attempt_id"], request["generation"], task["id"], mission["id"]):
        identifier(value)
    text(mission["title"], 160)
    text(mission["objective"], 4000)
    worker = task["worker_id"]
    if (request["schema"] != "pepeuch.control-plane/execution-request/v1"
            or task["schema"] != "pepeuch.control-plane/task/v1" or task["role"] != "demo-report"
            or task["capability"] != "demo.report.v1" or task["state"] != "running"
            or task["simulated"] is not True or task["mission_id"] != mission["id"]
            or not isinstance(worker, str) or worker != "fake-cpu" and re.fullmatch(r"n_[0-9a-f]{32}", worker) is None):
        raise Problem("invalid_worker_response")
    refs = request["authorized_files"]
    if not isinstance(refs, list) or len(refs) > 32:
        raise Problem("invalid_worker_response")
    for reference in refs:
        identifier(reference)
    if request["expected_version"] is not None:
        identifier(request["expected_version"])
    if type(request["deadline"]) not in (int, float) or not 0 < request["deadline"] <= 253402300799:
        raise Problem("invalid_worker_response")
    try:
        if not isinstance(request["started_at"], str) or len(request["started_at"]) > 64 or datetime.fromisoformat(request["started_at"]).utcoffset() is None:
            raise ValueError()
    except ValueError:
        raise Problem("invalid_worker_response") from None
