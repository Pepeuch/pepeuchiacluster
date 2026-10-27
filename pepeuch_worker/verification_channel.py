"""Inherited root-peer channel; never trusts a worker-owned proof file or boolean.

No listener, installation, privilege change or service is started here. A future
authorized one-shot controller must supply the connected FD before restrictions.
"""

import math
import os
import secrets
import socket
import struct
import time

from control_plane.contracts import Problem, canonical, decode_json, fields
from .verification import CHECKS, digest
from .linux_observer import collect


REQUEST = "pepeuch.worker/verification-request/v1"
REPLY = "pepeuch.worker/verification-decision/v1"
MAX_FRAME = 131072


def transfer(sock, raw=None, *, root_only=False):
    deadline = time.monotonic() + 2
    writer = None
    if root_only:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
    def receive(size):
        nonlocal writer
        parts = bytearray()
        while len(parts) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Problem("os_isolation_not_verified", 503)
            sock.settimeout(remaining)
            if root_only:
                part, ancillary, flags, _ = sock.recvmsg(size - len(parts), socket.CMSG_SPACE(struct.calcsize("3i")))
                credentials = []
                unexpected = False
                for level, kind, value in ancillary:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_CREDENTIALS and len(value) == struct.calcsize("3i"):
                        credentials.append(struct.unpack("3i", value))
                    else:
                        unexpected = True
                        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                            import array
                            descriptors = array.array("i")
                            descriptors.frombytes(value[:len(value) - len(value) % descriptors.itemsize])
                            for fd in descriptors:
                                os.close(fd)
                if (flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC) or unexpected or len(credentials) != 1
                        or credentials[0][0] <= 0 or credentials[0][1:] != (0, 0)
                        or writer is not None and writer != credentials[0]):
                    raise Problem("os_isolation_not_verified", 503)
                writer = credentials[0]
            else:
                part = sock.recv(size - len(parts))
            if not part:
                raise Problem("os_isolation_not_verified", 503)
            parts.extend(part)
        return bytes(parts)
    if raw is not None:
        payload = canonical(raw).encode()
        if len(payload) > MAX_FRAME:
            raise Problem("os_isolation_not_verified", 503)
        sock.settimeout(2)
        sock.sendall(struct.pack("!I", len(payload)) + payload)
    size = struct.unpack("!I", receive(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise Problem("os_isolation_not_verified", 503)
    value = decode_json(receive(size))
    return (value, writer) if root_only else value


def validate_decision(reply, request, *, now):
    """Scope validation only, to be called AFTER kernel peer authentication."""
    fields(reply, ("schema", "nonce", "context_sha256", "configuration_sha256", "profile", "policy_sha256",
                   "issued_monotonic", "expires_monotonic", "decision", "guarantees", "receipt_sha256"))
    if (reply["schema"] != REPLY or reply["nonce"] != request["nonce"] or reply["decision"] != "permit"
            or reply["context_sha256"] != digest(request["context"])
            or reply["configuration_sha256"] != digest(request["configuration"])
            or reply["profile"] != request["configuration"]["os_profile"]["schema"]):
        raise Problem("os_isolation_not_verified", 503)
    for name in ("policy_sha256", "receipt_sha256"):
        value = reply[name]
        if not isinstance(value, str) or len(value) != 64 or value == "0" * 64 or any(c not in "0123456789abcdef" for c in value):
            raise Problem("os_isolation_not_verified", 503)
    issued, expires = reply["issued_monotonic"], reply["expires_monotonic"]
    if (any(type(t) not in (int, float) or not math.isfinite(t) for t in (issued, expires, now))
            or not issued <= now < expires <= issued + 2):
        raise Problem("os_isolation_not_verified", 503)
    guarantees = reply["guarantees"]
    if not isinstance(guarantees, dict) or set(guarantees) != set(CHECKS):
        raise Problem("os_isolation_not_verified", 503)
    for item in guarantees.values():
        fields(item, ("enforced", "verified", "evidence_sha256"))
        if (item["enforced"] is not True or item["verified"] is not True
                or not isinstance(item["evidence_sha256"], str) or len(item["evidence_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["evidence_sha256"])):
            raise Problem("os_isolation_not_verified", 503)


class VerificationSession:
    def __init__(self, configuration, descriptor, *, observer=collect):
        from .contracts import configuration as validate_configuration
        self.configuration = validate_configuration(configuration)
        self.descriptor, self.observer = descriptor, observer
        self.context = None
        self.writer = None
        self.policy_sha256 = None

    def check(self):
        duplicate = None
        try:
            if type(self.descriptor) is not int or not 3 <= self.descriptor <= 1024:
                raise Problem("os_isolation_not_verified", 503)
            duplicate = os.dup(self.descriptor)
            with socket.socket(fileno=duplicate) as peer:
                duplicate = None
                if peer.family != socket.AF_UNIX or peer.type != socket.SOCK_STREAM:
                    raise Problem("os_isolation_not_verified", 503)
                pid, uid, gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                if pid <= 0 or uid != 0 or gid != 0:
                    raise Problem("os_isolation_not_verified", 503)
                # Require an initial-namespace controller, not namespace-local root.
                from .linux_observer import bounded
                if bounded("/proc/self/uid_map", 256).split() != ["0", "0", "4294967295"]:
                    raise Problem("os_isolation_not_verified", 503)
                observations = self.observer(self.configuration)
                if observations.get("synthetic") is not False or observations.get("stable") is not True or observations.get("unavailable"):
                    raise Problem("os_isolation_not_verified", 503)
                context = observations["process"]
                profile = self.configuration["os_profile"]
                status = context.get("status") or {}
                if (context.get("pid") != os.getpid() or os.getuid() != os.geteuid() or os.getgid() != os.getegid()
                        or os.geteuid() != profile["expected_uid"] or os.getegid() != profile["expected_gid"]
                        or os.geteuid() == 0 or os.getegid() == 0 or os.geteuid() == profile["backend_uid"]
                        or observations.get("configuration_sha256") != digest(self.configuration)
                        or status.get("Uid") != [profile["expected_uid"]] * 4
                        or status.get("Gid") != [profile["expected_gid"]] * 4 or status.get("NoNewPrivs") != 1
                        or any(status.get(name) != 0 for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"))):
                    raise Problem("os_isolation_not_verified", 503)
                if self.context is not None and digest(self.context) != digest(context):
                    raise Problem("os_isolation_not_verified", 503)
                request = {"schema": REQUEST, "nonce": secrets.token_hex(32), "configuration": self.configuration,
                           "context": context}
                reply, writer = transfer(peer, request, root_only=True)
                validate_decision(reply, request, now=time.monotonic())
                if (self.writer is not None and self.writer != writer
                        or self.policy_sha256 is not None and self.policy_sha256 != reply["policy_sha256"]):
                    raise Problem("os_isolation_not_verified", 503)
                from copy import deepcopy
                self.context = deepcopy(context)
                self.writer, self.policy_sha256 = writer, reply["policy_sha256"]
        except (Problem, OSError, ValueError, TypeError, KeyError, AttributeError, struct.error):
            raise Problem("os_isolation_not_verified", 503) from None
        finally:
            if duplicate is not None:
                os.close(duplicate)
