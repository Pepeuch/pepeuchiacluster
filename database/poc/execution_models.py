"""B4.4 typed plans/results and safe manifests, outside all B2 payloads."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Any, Callable

from discovery_cache import canonical_json, validate_snapshot
from metadata_primitives import copy_metadata
from source_spec_design import SOURCE_SPECS


class Status(str, Enum):
    SUCCESS = "success"
    UNCHANGED = "unchanged"  # Reserved for a future validated same-scope cache.
    DEFERRED = "deferred"
    FAILED = "failed"


class Reason(str, Enum):
    AUTHENTICATION = "authentication_refused"
    FORBIDDEN = "access_forbidden"
    TARGET_UNAVAILABLE = "target_unavailable"
    NIM_TAG_UNAVAILABLE = "metadata_unavailable_for_tag"
    QUOTA = "temporary_quota"
    PROVIDER = "temporary_provider_error"
    HTTP_ERROR = "http_error"
    REDIRECT = "redirect_rejected"
    CACHE_REQUIRED = "validated_cache_required"
    TIMEOUT = "timeout"
    CONNECTION = "connection_interrupted"
    INVALID_JSON = "invalid_json_or_response"
    INVALID_SCHEMA = "invalid_schema"
    IDENTITY = "identity_mismatch"
    SELECTION = "selection_forbidden"
    INCOMPLETE = "selection_incomplete"
    REQUEST_BUDGET = "request_budget_exhausted"
    ATTEMPT_BUDGET = "attempt_budget_exhausted"
    TIME_BUDGET = "time_budget_exhausted"
    RETRY_AFTER_BUDGET = "retry_after_exceeds_time_budget"
    RETRY_AFTER_EXTREME = "retry_after_excessive"
    DELAY_LIMIT = "retry_delay_exceeds_policy"
    WAIT_INTERRUPTED = "retry_wait_interrupted"
    RUNTIME = "invalid_execution_runtime"
    UNEXPECTED = "unexpected_error"


class ExecutionError(Exception):
    def __init__(self, reason: Reason):
        if not isinstance(reason, Reason):
            raise ValueError("Normalized execution reason required")
        self.reason = reason
        super().__init__(reason.value)


def number(value: Any, *, positive: bool = False) -> float:
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
        result = float(value) if valid else -1.0
    except OverflowError:
        result = -1.0
    if result < 0 or (positive and result == 0):
        raise ValueError("Finite execution budget value required")
    return result


def _identifier(value: Any) -> str:
    # Deliberately public identifiers only: never a URL, query or auth value.
    if (not isinstance(value, str) or len(value) > 256
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ValueError("Non-sensitive resource identifier required")
    return value


@dataclass(frozen=True, order=True)
class ResourceRef:
    source: str
    source_id: str

    def __post_init__(self):
        if self.source not in SOURCE_SPECS:
            raise ValueError("Registered source required")
        _identifier(self.source_id)


def safe_selection(source: str, value: Any) -> dict[str, Any]:
    """Accept only the current source's non-sensitive B2 selection vocabulary."""
    if source not in SOURCE_SPECS or not isinstance(value, dict):
        raise ValueError("Registered source selection required")
    scope = copy_metadata(value)
    spec = SOURCE_SPECS[source]
    mode = scope.get("mode")
    if not isinstance(mode, str) or mode not in spec.selection_modes:
        raise ValueError("Unsupported execution selection")
    fields = {"mode"}
    if mode == "exact_ids":
        fields.add("ids")
        ids = scope.get("ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids) or len(set(ids)) != len(ids):
            raise ValueError("Distinct selected IDs required")
        for identity in ids:
            _identifier(identity)
    elif mode in ("first_n_sorted", "first_n_unique"):
        fields.add("limit")
        if type(scope.get("limit")) is not int or scope["limit"] < 0:
            raise ValueError("Nonnegative selection limit required")
    else:
        fields.update({"resource_id", "tag"})
        _identifier(scope.get("resource_id"))
        if not isinstance(scope.get("tag"), str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", scope["tag"]):
            raise ValueError("Container tag selection required")
    if source in ("modelscope", "csghub"):
        fields.add("endpoint")
        if scope.get("endpoint") not in {f"https://{host}" for host in spec.transport.configured_hosts}:
            raise ValueError("Configured metadata endpoint required")
    if source == "csghub":
        fields.update({"source", "revision_request"})
        if scope.get("source") != "csg" or scope.get("revision_request") != "main":
            raise ValueError("Explicit CSGHub scope required")
    if source == "moark":
        fields.update({"endpoint", "catalog_url", "authentication", "input"})
        if (scope.get("endpoint") != "https://moark.ai/v1"
                or scope.get("catalog_url") != "https://moark.ai/v1/models?type=text2text&include_details=false"
                or scope.get("authentication") != "anonymous"
                or scope.get("input") not in ("synthetic_fixture", "public_api")):
            raise ValueError("Explicit MoArk scope required")
    if set(scope) != fields:
        raise ValueError("Unexpected or sensitive selection fields")
    return scope


@dataclass(frozen=True)
class ExecutionPolicy:
    max_requests: int
    max_attempts: int
    total_seconds: float
    max_delay_seconds: float
    backoff_seconds: float
    resources: frozenset[ResourceRef]
    retry_http_statuses: frozenset[int]
    retry_transport_errors: bool

    def __post_init__(self):
        if type(self.max_requests) is not int or self.max_requests < 0 or type(self.max_attempts) is not int or self.max_attempts < 1:
            raise ValueError("Explicit request and attempt limits required")
        number(self.max_requests)
        number(self.max_attempts, positive=True)
        number(self.total_seconds, positive=True)
        number(self.max_delay_seconds)
        number(self.backoff_seconds)
        if self.backoff_seconds > self.max_delay_seconds:
            raise ValueError("Initial backoff exceeds delay limit")
        resources = frozenset(self.resources)
        statuses = frozenset(self.retry_http_statuses)
        if not resources or any(not isinstance(ref, ResourceRef) for ref in resources):
            raise ValueError("Explicit resource allowlist required")
        if (any(type(code) is not int for code in statuses) or not statuses <= {429, 500, 502, 503, 504}
                or type(self.retry_transport_errors) is not bool):
            raise ValueError("Only explicitly transient errors may be retried")
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "retry_http_statuses", statuses)


@dataclass(frozen=True)
class ExecutionRuntime:
    monotonic: Callable[[], float]
    wall_time: Callable[[], float]
    sleep: Callable[[float], None]
    jitter: Callable[[float], float]  # Nonnegative additional seconds, then capped.

    def __post_init__(self):
        if any(not callable(value) for value in (self.monotonic, self.wall_time, self.sleep, self.jitter)):
            raise ValueError("Explicit clock, wait and jitter dependencies required")


@dataclass(frozen=True)
class SourceObservation:
    snapshot: dict[str, Any]
    complete: bool


def _planned_resources(source, scope, resources) -> tuple[ResourceRef, ...]:
    refs = tuple(resources)
    if (not refs or any(not isinstance(ref, ResourceRef) or ref.source != source for ref in refs)
            or len(set(refs)) != len(refs)):
        raise ValueError("Distinct resources of this source required")
    ids = {ref.source_id for ref in refs}
    if scope["mode"] == "exact_ids" and ids != set(scope["ids"]):
        raise ValueError("Planned resources differ from the selection")
    if scope["mode"] == "exact_tag" and ids != {scope["resource_id"]}:
        raise ValueError("One selected resource/tag required")
    return refs


@dataclass(frozen=True)
class SourceTask:
    source: str
    selection: dict[str, Any]
    resources: tuple[ResourceRef, ...]
    policy: ExecutionPolicy
    operation: Callable[..., SourceObservation]
    idempotent: bool
    synthetic: bool

    def __post_init__(self):
        scope = safe_selection(self.source, self.selection)
        refs = _planned_resources(self.source, scope, self.resources)
        if not isinstance(self.policy, ExecutionPolicy) or not callable(self.operation):
            raise ValueError("Execution policy and explicit operation required")
        if type(self.idempotent) is not bool or type(self.synthetic) is not bool:
            raise ValueError("Explicit idempotence and data provenance required")
        if self.source == "moark" and self.synthetic != (scope["input"] == "synthetic_fixture"):
            raise ValueError("Inconsistent MoArk execution provenance")
        object.__setattr__(self, "selection", scope)
        object.__setattr__(self, "resources", refs)


def validate_observation(source, selection, resources, snapshot) -> dict[str, Any]:
    data = copy_metadata(snapshot)
    validate_snapshot(data)
    if canonical_json(data["scope"]) != canonical_json({source: selection}):
        raise ExecutionError(Reason.IDENTITY)
    if any(record["source"] != source or record["entity_type"] not in SOURCE_SPECS[source].entity_types for record in data["records"]):
        raise ExecutionError(Reason.IDENTITY)
    spec = SOURCE_SPECS[source]
    if any((record["source_revision"] is None and not spec.revision_nullable)
           or (record["source_revision"] is not None and spec.revision_kind == "none") for record in data["records"]):
        raise ExecutionError(Reason.INVALID_SCHEMA)
    actual = {record["source_id"] for record in data["records"]}
    expected = {ref.source_id for ref in resources}
    if actual - expected:
        raise ExecutionError(Reason.IDENTITY)
    if expected - actual:
        raise ExecutionError(Reason.INCOMPLETE)
    if selection["mode"] == "exact_tag" and any(record["source_revision"] != selection["tag"] for record in data["records"]):
        raise ExecutionError(Reason.IDENTITY)
    return data


@dataclass(frozen=True)
class SourceResult:
    source: str
    selection: dict[str, Any]
    resources: tuple[ResourceRef, ...]
    status: Status
    reason: Reason | None
    last_error: Reason | None
    attempts: int
    requests: int
    elapsed_seconds: float
    wait_seconds: float
    policy: ExecutionPolicy
    idempotent: bool
    synthetic: bool
    complete: bool
    snapshot: dict[str, Any] | None

    def __post_init__(self):
        object.__setattr__(self, "selection", safe_selection(self.source, self.selection))
        object.__setattr__(self, "resources", _planned_resources(self.source, self.selection, self.resources))
        if not isinstance(self.policy, ExecutionPolicy):
            raise ValueError("Explicit result budget policy required")
        if not isinstance(self.status, Status) or (self.reason is not None and not isinstance(self.reason, Reason)):
            raise ValueError("Normalized result state/reason required")
        if self.last_error is not None and not isinstance(self.last_error, Reason):
            raise ValueError("Normalized last error required")
        if (type(self.attempts) is not int or not 0 <= self.attempts <= self.policy.max_attempts
                or type(self.requests) is not int or not 0 <= self.requests <= self.policy.max_requests):
            raise ValueError("Invalid execution counters")
        number(self.elapsed_seconds)
        number(self.wait_seconds)
        if any(type(value) is not bool for value in (self.idempotent, self.synthetic, self.complete)):
            raise ValueError("Explicit execution flags required")
        if self.status in (Status.SUCCESS, Status.UNCHANGED):
            if not self.complete or self.reason is not None or self.snapshot is None:
                raise ValueError("Positive result requires a complete validated snapshot")
            if not set(self.resources) <= self.policy.resources:
                raise ValueError("Positive result resources must be authorized")
            object.__setattr__(self, "snapshot", validate_observation(self.source, self.selection, self.resources, self.snapshot))
        elif self.complete or self.snapshot is not None or self.reason is None:
            raise ValueError("Failed/deferred result cannot publish a snapshot")

    def to_manifest(self) -> dict[str, Any]:
        # Revalidate mutable nested snapshots before reporting their identity.
        snapshot = None if self.snapshot is None else validate_observation(self.source, self.selection, self.resources, self.snapshot)
        return copy_metadata({
            "source": self.source, "selection": safe_selection(self.source, self.selection),
            "status": self.status.value, "complete": self.complete,
            "synthetic": self.synthetic, "idempotent": self.idempotent,
            "requested_resources": [{"source": ref.source, "source_id": ref.source_id} for ref in self.resources],
            "attempts": self.attempts, "reason": None if self.reason is None else self.reason.value,
            "last_error": None if self.last_error is None else self.last_error.value,
            "snapshot_id": None if snapshot is None else snapshot["snapshot_id"],
            "budget": {
                "requests_used": self.requests, "max_requests": self.policy.max_requests,
                "max_attempts": self.policy.max_attempts, "elapsed_seconds": self.elapsed_seconds,
                "total_seconds": self.policy.total_seconds, "wait_seconds": self.wait_seconds,
                "overrun": self.elapsed_seconds >= self.policy.total_seconds,
                "max_delay_seconds": self.policy.max_delay_seconds, "backoff_seconds": self.policy.backoff_seconds,
                "retry_http_statuses": sorted(self.policy.retry_http_statuses),
                "retry_transport_errors": self.policy.retry_transport_errors,
                "resources": [{"source": ref.source, "source_id": ref.source_id} for ref in sorted(self.policy.resources)],
            },
        })


@dataclass(frozen=True)
class ExecutionReport:
    results: tuple[SourceResult, ...]

    def __post_init__(self):
        results = tuple(self.results)
        if not results or any(not isinstance(result, SourceResult) for result in results) or len({r.source for r in results}) != len(results):
            raise ValueError("One result per requested source required")
        object.__setattr__(self, "results", results)

    def to_manifest(self) -> dict[str, Any]:
        kinds = {r.synthetic for r in self.results}
        return {
            "format": "pepeuch-ai.discovery-execution/v1",
            "data_kind": "synthetic" if kinds == {True} else "real" if kinds == {False} else "mixed",
            "requested_sources": [result.source for result in self.results],
            "complete": all(result.complete for result in self.results),
            "sources": [result.to_manifest() for result in self.results],
        }

    def successful_snapshots(self) -> dict[str, dict[str, Any]]:
        return {r.source: validate_observation(r.source, r.selection, r.resources, r.snapshot)
                for r in self.results if r.status in (Status.SUCCESS, Status.UNCHANGED)}
