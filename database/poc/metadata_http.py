"""B4.2: one bounded anonymous metadata GET; no retry or provider semantics."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from metadata_primitives import assert_secret_free, copy_metadata, strict_json_loads


class MetadataResponseError(ValueError):
    pass


class MetadataNetworkError(OSError):
    pass


class MetadataTimeoutError(TimeoutError):
    pass


class MetadataHTTPError(HTTPError):
    """HTTPError-compatible status, without response body, headers or URL."""

    def __init__(self, status: int):
        super().__init__("", status, "Metadata HTTP request failed", {}, None)


@dataclass(frozen=True)
class HTTPPolicy:
    allowed_hosts: frozenset[str]
    max_response_bytes: int
    timeout_seconds: float

    def __post_init__(self):
        if not isinstance(self.allowed_hosts, (set, frozenset, tuple, list)):
            raise ValueError("Explicit metadata host collection required")
        hosts = frozenset(self.allowed_hosts)
        if not hosts or any(not isinstance(host, str) or not host or host != host.lower()
                            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host)
                            or host.startswith(".") or host.endswith(".") for host in hosts):
            raise ValueError("Explicit lowercase metadata hosts required")
        if type(self.max_response_bytes) is not int or self.max_response_bytes <= 0:
            raise ValueError("Positive metadata byte limit required")
        if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 60):
            raise ValueError("Metadata timeout must be positive and at most 60 seconds")
        object.__setattr__(self, "allowed_hosts", hosts)


@dataclass(frozen=True)
class HTTPResult:
    status: int
    body: bytes


class MetadataTransport(Protocol):
    def fetch(self, request: Request, *, timeout: float, max_bytes: int) -> HTTPResult:
        """Make exactly one bounded GET; never follow redirects or retry."""
        ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Inject an opener for offline tests; default has no cookie/auth handler."""

    def __init__(self, opener=None):
        self.opener = opener

    def fetch(self, request: Request, *, timeout: float, max_bytes: int) -> HTTPResult:
        opener = self.opener if self.opener is not None else build_opener(NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            # urllib normally raises HTTPError first, but explicit status checks
            # also protect injected openers. Do not read error/redirect bodies.
            body = response.read(max_bytes + 1) if status == 200 else b""
        return HTTPResult(status, body)


def _validate_url(url: str, policy: HTTPPolicy) -> None:
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValueError("Metadata URL not permitted")
    try:
        parts = urlsplit(url)
        permitted = (parts.scheme == "https" and parts.hostname in policy.allowed_hosts
                     and parts.port in (None, 443) and parts.username is None
                     and parts.password is None and "#" not in url)
        if not permitted:
            raise ValueError("Metadata URL not permitted")
        # Filters are allowed; credentials in URL query parameters are not.
        assert_secret_free({key: None for key, _value in parse_qsl(parts.query, keep_blank_values=True)})
    except (ValueError, TypeError):
        raise ValueError("Metadata URL not permitted") from None


def get_metadata_json(url: str, *, policy: HTTPPolicy, transport: MetadataTransport | None = None) -> dict[str, Any]:
    """Validate origin before I/O; return a detached, secret-free JSON object.

    Timeout is the urllib socket timeout, not an end-to-end execution deadline.
    Retry budgets, per-host concurrency, DNS pinning and authenticated scopes
    are deliberately outside this primitive.
    """
    _validate_url(url, policy)
    request = Request(url, headers={
        "Accept": "application/json", "User-Agent": "Pepeuch-AI-Discovery-POC/0.1",
    }, method="GET")
    try:
        result = (transport if transport is not None else UrllibTransport()).fetch(
            request, timeout=policy.timeout_seconds, max_bytes=policy.max_response_bytes,
        )
    except HTTPError as exc:
        status = exc.code
        # Release any HTTP error stream without reading or retaining its body.
        try:
            exc.close()
        except OSError:
            pass
        if type(status) is not int or not 100 <= status <= 599:
            raise MetadataNetworkError("Invalid metadata HTTP status") from None
        raise MetadataHTTPError(status) from None
    except TimeoutError:
        raise MetadataTimeoutError("Metadata request timed out") from None
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise MetadataTimeoutError("Metadata request timed out") from None
        raise MetadataNetworkError("Metadata network unavailable") from None
    except OSError:
        raise MetadataNetworkError("Metadata network unavailable") from None
    if not isinstance(result, HTTPResult) or type(result.status) is not int or not 100 <= result.status <= 599:
        raise MetadataResponseError("Invalid metadata HTTP result")
    if result.status != 200:
        raise MetadataHTTPError(result.status)
    if not isinstance(result.body, bytes):
        raise MetadataResponseError("Metadata response must be bytes")
    if len(result.body) > policy.max_response_bytes:
        raise MetadataResponseError("Metadata response exceeded size limit")
    try:
        data = strict_json_loads(result.body)
        if not isinstance(data, dict):
            raise ValueError("Metadata response must be an object")
        return copy_metadata(data)
    except (ValueError, TypeError, UnicodeError):
        raise MetadataResponseError("Invalid metadata JSON response") from None
