"""Versioned application contracts and strict, bounded wire primitives."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from typing import ClassVar, Protocol
from uuid import UUID, uuid4


class Problem(Exception):
    """Only public codes cross the HTTP boundary; never interpolate input."""
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def decode_json(raw):
    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError()
        return parsed
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=finite,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise Problem("invalid_json") from None


def fields(data, required, optional=()):
    if not isinstance(data, dict) or not set(required) <= set(data) or set(data) - set(required) - set(optional):
        raise Problem("invalid_fields")
    return data


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\0" in value:
        raise Problem("invalid_text")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise Problem("invalid_text") from None
    return value


def operation_id(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise Problem("invalid_operation_id") from None
    return value


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-z]_[0-9a-f]{32}", value) is None:
        raise Problem("invalid_identifier")
    return value


def new_id(prefix):
    return prefix + "_" + uuid4().hex


def timestamp(epoch):
    if isinstance(epoch, bool) or not isinstance(epoch, (int, float)) or not math.isfinite(epoch) or epoch < 0:
        raise Problem("invalid_clock", 500)
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="microseconds")


STATES = frozenset({"draft", "approved", "queued", "running", "completed", "failed",
                    "cancel_requested", "cancelled", "interrupted"})
TRANSITIONS = {
    "draft": {"approved", "cancelled"}, "approved": {"queued", "cancelled"},
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "cancel_requested", "interrupted"},
    "cancel_requested": {"cancelled", "interrupted"},
    "failed": {"queued"}, "interrupted": {"queued", "cancelled"},
    "completed": set(), "cancelled": set(),
}


class Contract:
    KIND: ClassVar[str]

    def to_dict(self):
        return {"schema": f"pepeuch.control-plane/{self.KIND}/v1", **asdict(self)}


@dataclass(frozen=True)
class Principal:
    identity: str
    role: str
    credential_epoch: int | None = None


@dataclass(frozen=True)
class WorkspaceReference(Contract):
    KIND: ClassVar[str] = "workspace-reference"
    id: str
    project: str


@dataclass(frozen=True)
class Mission(Contract):
    KIND: ClassVar[str] = "mission"
    id: str
    owner: str
    project: str
    workspace: dict
    title: str
    objective: str
    state: str
    created_at: str
    authorized_files: list
    provenance: dict


@dataclass(frozen=True)
class Task(Contract):
    KIND: ClassVar[str] = "task"
    id: str
    mission_id: str
    role: str
    capability: str
    worker_id: str
    state: str
    simulated: bool = True


@dataclass(frozen=True)
class Attempt(Contract):
    KIND: ClassVar[str] = "attempt"
    id: str
    task_id: str
    number: int
    worker_id: str
    state: str
    started_at: str
    deadline: float
    error_code: str | None


@dataclass(frozen=True)
class ExecutionResult(Contract):
    KIND: ClassVar[str] = "execution-result"
    attempt_id: str
    generation: str
    status: str
    outputs: list
    error_code: str | None = None

    @classmethod
    def from_dict(cls, data):
        fields(data, ("schema", "attempt_id", "generation", "status", "outputs", "error_code"))
        if data["schema"] != "pepeuch.control-plane/execution-result/v1":
            raise Problem("invalid_schema")
        identifier(data["attempt_id"])
        identifier(data["generation"])
        if not isinstance(data["status"], str) or data["status"] not in {"completed", "failed", "interrupted", "cancelled"}:
            raise Problem("invalid_result_state")
        if not isinstance(data["outputs"], list) or len(data["outputs"]) > 1:
            raise Problem("invalid_outputs")
        if data["error_code"] is not None and (not isinstance(data["error_code"], str) or data["error_code"] not in {"simulated_failure", "simulated_interruption"}):
            raise Problem("invalid_error_code")
        return cls(**{key: value for key, value in data.items() if key != "schema"})


@dataclass(frozen=True)
class AuditEvent(Contract):
    KIND: ClassVar[str] = "audit-event"
    id: str
    sequence: int
    mission_id: str | None
    workspace_id: str
    actor: str
    at: str
    type: str
    details: dict


class Coordinator(Protocol):
    def plan(self, mission: dict, workers: tuple[dict, ...]) -> dict: ...


class Executor(Protocol):
    def execute(self, request: dict, *, mode: str = "success") -> ExecutionResult: ...
