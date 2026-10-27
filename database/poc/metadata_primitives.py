"""B4.1 domain-neutral metadata safety; no provider/access/identity policy."""

from __future__ import annotations

import json
import math
from typing import Any, Callable
from urllib.error import HTTPError


_SECRET_KEYS = frozenset({
    "apikey", "xapikey", "apitoken", "accesstoken", "refreshtoken", "idtoken",
    "authorization", "proxyauthorization", "credentials", "password", "passwd",
    "secret", "clientsecret", "apisecret", "secretkey", "privatekey", "token",
    "sessiontoken", "bearertoken", "cookie", "setcookie",
})


def object_value(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def optional_nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer or null")
    return value


def assert_secret_free(value: Any) -> None:
    """Reject credential-like field names recursively, without logging values.

    This is a metadata boundary, not an arbitrary-text secret detector. Token
    counts and tokenizer names remain valid. Track ancestors rather than all
    visited objects: repeated ordinary subobjects are valid; cycles are not.
    """
    def visit(node: Any, ancestors: set[int]) -> None:
        if not isinstance(node, (dict, list, tuple)):
            return
        identity = id(node)
        if identity in ancestors:
            raise ValueError("Metadata must be acyclic JSON data")
        ancestors.add(identity)
        try:
            if isinstance(node, dict):
                for key, child in node.items():
                    if not isinstance(key, str):
                        raise ValueError("Metadata keys must be strings")
                    folded = "".join(c for c in key.casefold() if c.isalnum())
                    if folded in _SECRET_KEYS:
                        raise ValueError("Refusing credential-like metadata")
                    visit(child, ancestors)
            else:
                for child in node:
                    visit(child, ancestors)
        finally:
            ancestors.remove(identity)
    try:
        visit(value, set())
    except RecursionError:
        raise ValueError("Metadata nesting exceeds supported depth") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


def _reject_constant(_value):
    raise ValueError("Nonfinite JSON number")


def strict_json_loads(payload: str | bytes) -> Any:
    """Decode UTF-8 JSON, refusing repeated keys and nonfinite numbers."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    try:
        return json.loads(payload, object_pairs_hook=_unique_object,
                          parse_float=_finite_float, parse_constant=_reject_constant)
    except RecursionError:
        raise ValueError("JSON nesting exceeds supported depth") from None


def copy_metadata(value: Any, *, default: Callable[[Any], Any] | None = None) -> Any:
    """JSON copy with explicit optional SDK conversion, finite values, no secrets."""
    assert_secret_free(value)
    try:
        result = strict_json_loads(json.dumps(value, ensure_ascii=False, allow_nan=False, default=default))
    except RecursionError:
        raise ValueError("Metadata nesting exceeds supported depth") from None
    # A supplied SDK serializer can introduce additional objects/field names.
    assert_secret_free(result)
    return result


def error_summary(source: str, exc: Exception) -> str:
    """Use a caller-owned label and exception class/status, never body or URL."""
    kind = type(exc).__name__
    if isinstance(exc, HTTPError) and type(exc.code) is int and 100 <= exc.code <= 599:
        kind = f"HTTP {exc.code}"
    return f"{source} metadata operation failed ({kind}); no snapshot written"
