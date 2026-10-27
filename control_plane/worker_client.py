"""Explicit local worker runner. No direct SQLite/filesystem business access."""

from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from .contracts import Executor, Problem, canonical, decode_json
from .demo import FakeWorker


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


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
        self.credential = credential
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def call(self, method, path, data=None):
        if not path.startswith("/api/v1/execution/") or "?" in path or "#" in path:
            raise Problem("invalid_worker_route")
        raw = None if data is None else canonical(data).encode()
        request = Request(self.base_url + path, data=raw, method=method,
                          headers={"Authorization": "Bearer " + self.credential, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(131073)
                if len(raw) > 131072:
                    raise Problem("invalid_worker_response")
                return decode_json(raw)
        except HTTPError as exc:
            exc.close()
            raise Problem("worker_request_refused", 409) from None
        except (URLError, OSError):
            raise Problem("backend_unavailable", 503) from None


class WorkerRunner:
    def __init__(self, client, executor: Executor | None = None):
        self.client = client
        self.executor = FakeWorker() if executor is None else executor

    def run_once(self, *, mode="success", before_execute=None):
        response = self.client.call("POST", "/api/v1/execution/claim", {"operation_id": str(uuid4())})
        request = response["request"]
        if request is None:
            return "idle"
        if mode == "hold":
            return "held"
        if before_execute is not None:
            before_execute(request)
        state = self.client.call("GET", "/api/v1/execution/" + request["attempt_id"] + "/state")["state"]
        if state not in {"running", "cancel_requested"}:
            return state
        result = self.executor.execute(request, mode="cancel" if state == "cancel_requested" else mode)
        self.client.call("POST", "/api/v1/execution/" + request["attempt_id"] + "/finish", result.to_dict())
        return result.status
