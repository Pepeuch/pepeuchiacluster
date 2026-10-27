"""Bounded loopback prototype HTTP adapter. No business logic in handlers.

Not a production HTTP stack. No cookies, CORS, proxy trust or LAN listener.
"""

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPMessage
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

from .auth import Authenticator, require_role
from .contracts import ExecutionResult, Problem, canonical, decode_json
from .http_io import DeadlineInput


@dataclass
class Response:
    body: object
    status: int = 200
    headers: dict = field(default_factory=dict)


class API:
    def __init__(self, service):
        self.service = service
        self.auth = Authenticator(service.store.root)

    def dispatch(self, method, path, principal, data=None):
        if method == "POST" and path == "/api/v1/execution/claim":
            return Response(self.service.execution.claim(principal, data))
        matched = re.fullmatch(r"/api/v1/execution/([a-z]_[0-9a-f]{32})/finish", path)
        if method == "POST" and matched:
            require_role(principal, "worker")
            return Response(self.service.execution.finish(principal, matched[1], ExecutionResult.from_dict(data)))
        matched = re.fullmatch(r"/api/v1/execution/([a-z]_[0-9a-f]{32})/state", path)
        if method == "GET" and matched:
            return Response(self.service.execution.state(principal, matched[1]))
        require_role(principal, "admin")
        if method == "GET" and path == "/api/v1/health":
            return Response({"schema": "pepeuch.control-plane/health/v1", "status": "ok",
                             "simulation_only": self.service.simulation_only(principal)})
        if path == "/api/v1/missions":
            if method == "GET":
                return Response({"missions": self.service.list_missions(principal)})
            if method == "POST":
                return Response(self.service.create_mission(principal, data), 201)
        if method == "POST" and path == "/api/v1/cpu-missions":
            return Response(self.service.create_cpu_mission(principal, data), 201)
        if method == "GET" and path == "/api/v1/workspaces":
            return Response({"workspaces": self.service.workspaces(principal)})
        if method == "GET" and path == "/api/v1/dashboard":
            return Response(self.service.dashboard(principal))
        if method == "GET" and path == "/api/v1/nodes":
            return Response({"nodes": self.service.execution.nodes(principal)})
        if method == "GET" and path == "/api/v1/workers":
            return Response({"workers": self.service.registry.list()})
        matched = re.fullmatch(r"/api/v1/workers/(fake-cpu|n_[0-9a-f]{32})/revoke", path)
        if method == "POST" and matched:
            return Response(self.service.revoke_worker(principal, matched[1], data))
        matched = re.fullmatch(r"/api/v1/workspaces/([a-z]_[0-9a-f]{32})/files", path)
        if matched:
            if method == "GET":
                return Response(self.service.workspace.list_files(principal, matched[1]))
            if method == "POST":
                return Response(self.service.workspace.upload(principal, matched[1], data), 201)
        matched = re.fullmatch(r"/api/v1/workspaces/([a-z]_[0-9a-f]{32})/files/([a-z]_[0-9a-f]{32})(?:/versions/([a-z]_[0-9a-f]{32}))?/download", path)
        if matched and method == "GET":
            raw, name, checksum = self.service.workspace.download(principal, *matched.groups())
            return Response(raw, headers={"Content-Type": "application/octet-stream",
                                         "Content-Disposition": f'attachment; filename="{name}"',
                                         "X-Content-SHA256": checksum})
        matched = re.fullmatch(r"/api/v1/missions/([a-z]_[0-9a-f]{32})/(approve|cancel|retry)", path)
        if method == "POST" and matched:
            return Response(getattr(self.service.execution, matched[2])(principal, matched[1], data))
        matched = re.fullmatch(r"/api/v1/missions/([a-z]_[0-9a-f]{32})(/events)?", path)
        if matched and method == "GET":
            identity, events = matched.groups()
            return Response({"events": self.service.events(principal, identity)} if events else self.service.get_mission(principal, identity))
        raise Problem("not_found", 404)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, api, *, port=8765, host="127.0.0.1", io_seconds=5, max_connections=16):
        if host != "127.0.0.1":
            raise Problem("loopback_only")
        self.api = api
        if type(io_seconds) not in (int, float) or not 0 < io_seconds <= 5 or type(max_connections) is not int or not 1 <= max_connections <= 16:
            raise Problem("invalid_http_limits")
        self.io_seconds = io_seconds
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__((host, port), Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(self.io_seconds)
        return connection, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Never print traceback, user-controlled path, request body or headers.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "PepeuchLocal/0.1"
    sys_version = ""

    def log_message(self, format, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self._respond(Response({"error": "invalid_http_request"}, code))

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def handle_one_request(self):
        # Deliberately small HTTP subset: CRLF, origin-form, no folded headers,
        # duplicates, HTTP/0.9, transfer coding, upgrade or persistent connection.
        self.request_version, self.command, self.requestline = "HTTP/1.1", "", ""
        self.close_connection = True
        reader = DeadlineInput(self.connection, seconds=self.server.io_seconds)
        try:
            raw = reader.readline(2049)
            if not raw:
                return
            if len(raw) > 2048:
                raise Problem("request_line_too_large", 414)
            match = re.fullmatch(rb"([A-Z]{1,16}) ([\x21-\x7e]+) (HTTP/1\.[01])\r\n", raw)
            if match is None:
                raise Problem("invalid_http_request")
            self.command, self.path, self.request_version = (part.decode("ascii") for part in match.groups())
            self.headers = HTTPMessage()
            total, count, seen = 0, 0, set()
            while True:
                line = reader.readline(4097)
                total += len(line)
                if len(line) > 4096 or total > 16384:
                    raise Problem("headers_too_large", 431)
                if line == b"\r\n":
                    break
                count += 1
                if count > 32:
                    raise Problem("headers_too_large", 431)
                header = re.fullmatch(rb"([!#$%&'*+.^_`|~0-9A-Za-z-]+):([\x20-\x7e]*)\r\n", line)
                if header is None:
                    raise Problem("invalid_http_request")
                name, value = (part.decode("ascii") for part in header.groups())
                if name.lower() in seen:
                    raise Problem("duplicate_header")
                seen.add(name.lower())
                self.headers[name] = value.strip(" ")
            if "transfer-encoding" in seen:
                raise Problem("invalid_body_framing")
            if "expect" in seen or "upgrade" in seen:
                raise Problem("unsupported_http_feature", 417)
            length = self.headers.get("Content-Length")
            if length is not None and re.fullmatch(r"[0-9]{1,8}", length) is None:
                raise Problem("invalid_body_framing")
            if length is not None and int(length) > 1_500_000:
                raise Problem("request_too_large", 413)
            if self.command != "POST" and length is not None and int(length) != 0:
                raise Problem("unexpected_body")
            if self.command not in {"GET", "POST"}:
                raise Problem("method_not_allowed", 405)
            previous = self.rfile
            self.rfile = reader
            try:
                self._handle()
            finally:
                self.rfile = previous
        except TimeoutError:
            self._respond(Response({"error": "http_timeout"}, 408))
        except Problem as exc:
            self._respond(Response({"error": exc.code}, exc.status))
        except (OSError, UnicodeError, ValueError):
            self._respond(Response({"error": "invalid_http_request"}, 400))

    def _handle(self):
        try:
            hosts = self.headers.get_all("Host", [])
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if len(hosts) != 1 or hosts[0] not in allowed:
                raise Problem("invalid_host", 403)
            origins = self.headers.get_all("Origin", [])
            if origins and origins != ["http://" + hosts[0]]:
                raise Problem("invalid_origin", 403)
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise Problem("invalid_origin", 403)
            parts = urlsplit(self.path)
            if parts.scheme or parts.netloc or parts.query or parts.fragment or "%" in self.path or not self.path.startswith("/"):
                raise Problem("invalid_path")
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8")}
            if self.command == "GET" and self.path in static:
                name, content_type = static[self.path]
                target = Path(__file__).parent / "web" / name
                if not target.is_file():
                    raise Problem("not_found", 404)
                return self._respond(Response(target.read_bytes(), headers={"Content-Type": content_type}))
            authorization = self.headers.get_all("Authorization", [])
            if len(authorization) != 1:
                raise Problem("authentication_required", 401)
            principal = self.server.api.auth.authenticate(authorization[0])
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get_all("Transfer-Encoding") or len(lengths) > 1:
                raise Problem("invalid_body_framing")
            data = None
            if self.command == "POST":
                if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]):
                    raise Problem("content_length_required", 411)
                size = int(lengths[0])
                if size > 1_500_000:
                    raise Problem("request_too_large", 413)
                if self.headers.get_all("Content-Type") != ["application/json"]:
                    raise Problem("json_required", 415)
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise Problem("incomplete_request")
                data = decode_json(raw)
            elif lengths and lengths != ["0"]:
                raise Problem("unexpected_body")
            response = self.server.api.dispatch(self.command, self.path, principal, data)
        except TimeoutError:
            response = Response({"error": "http_timeout"}, 408)
        except Problem as exc:
            response = Response({"error": exc.code}, exc.status)
        except Exception:
            response = Response({"error": "operation_failed"}, 500)
        self._respond(response)

    def _respond(self, response):
        raw = response.body if isinstance(response.body, bytes) else canonical(response.body).encode()
        self.close_connection = True
        try:
            self.send_response(response.status)
            headers = {
                "Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(raw)),
                "Connection": "close", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin", "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                **response.headers,
            }
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(raw)
        except (OSError, ValueError):
            pass
