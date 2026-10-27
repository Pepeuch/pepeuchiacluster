"""B5.3 independent worker policy and evidence, separate from API credentials."""

from dataclasses import asdict, dataclass
from copy import deepcopy
from urllib.parse import urlsplit
import re

from control_plane.capabilities import CPU_DIGEST
from control_plane.contracts import Problem, fields


CONFIG_SCHEMA = "pepeuch.worker/config/v1"
EVIDENCE_SCHEMA = "pepeuch.worker/security-evidence/v1"
CPU_PROFILE = "linux-systemd-cpu/v1"


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Problem("invalid_worker_policy")
    return value


def configuration(data):
    fields(data, ("schema", "worker_id", "backend_url", "capabilities", "tools", "limits", "os_profile"))
    if data["schema"] != CONFIG_SCHEMA or not isinstance(data["worker_id"], str) or re.fullmatch(r"n_[0-9a-f]{32}", data["worker_id"]) is None:
        raise Problem("invalid_worker_configuration")
    try:
        if not isinstance(data["backend_url"], str) or re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", data["backend_url"]) is None:
            raise ValueError()
        endpoint = urlsplit(data["backend_url"])
        if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port
                or endpoint.username is not None or endpoint.password is not None
                or endpoint.path or endpoint.query or endpoint.fragment):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Problem("worker_loopback_only") from None
    if data["capabilities"] != [CPU_DIGEST] or data["tools"] != []:
        raise Problem("unsupported_worker_capabilities")
    limits = fields(data["limits"], ("input_bytes", "output_bytes", "seconds", "tasks"))
    integer(limits["input_bytes"], 1, 16000)
    integer(limits["output_bytes"], 1, 65536)
    integer(limits["seconds"], 1, 30)
    integer(limits["tasks"], 1, 1)
    profile = fields(data["os_profile"], ("schema", "expected_uid", "expected_gid", "backend_uid"))
    if profile["schema"] != CPU_PROFILE:
        raise Problem("unsupported_os_profile")
    for name in ("expected_uid", "expected_gid", "backend_uid"):
        integer(profile[name], 0, 2 ** 31 - 1)
    return deepcopy(data)


@dataclass(frozen=True)
class SecurityProperty:
    declared: object
    enforced: bool | None
    verified: bool
    evidence: str

    def __post_init__(self):
        if self.enforced is not None and type(self.enforced) is not bool or type(self.verified) is not bool:
            raise Problem("invalid_security_evidence")
        if self.verified and self.enforced is not True:
            raise Problem("verification_requires_enforcement")

    def to_dict(self):
        return asdict(self)


def require_verified(properties):
    """Declared settings and untrusted booleans can never grant readiness."""
    if not properties or any(not isinstance(p, SecurityProperty) or not p.verified or p.enforced is not True for p in properties.values()):
        raise Problem("os_isolation_not_verified", 503)
