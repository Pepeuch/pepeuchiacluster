"""B4.5 POSIX local, append-only atomic checkpoints; one writer per directory.

Never use on NFS/SMB or an untrusted shared directory. No automatic recovery,
latest pointer, history pruning or database access. Linux is the tested target.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import secrets
import stat

from discovery_cache import canonical_json, digest
from metadata_primitives import copy_metadata, strict_json_loads
from validated_discovery_cache import _request, validate_cache
from discovery_provenance import publication_guard


FORMAT = "pepeuch-ai.discovery-checkpoint/v1"
MAX_BYTES = 16 * 1024 * 1024
ID = re.compile(r"[0-9a-f]{64}\.[0-9a-f]{64}")


@contextmanager
def _directory(root):
    raw = os.fspath(root)
    if not isinstance(raw, str) or not raw.startswith("/") or ".." in raw.split("/"):
        raise ValueError("Absolute local checkpoint directory required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for component in Path(raw).parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("Checkpoint directory must be private and owned by the current user")
        yield fd
    finally:
        os.close(fd)


def _regular(fd):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("Private regular checkpoint file required")
    return info


def _read(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
    try:
        info = _regular(fd)
        if info.st_size > MAX_BYTES:
            raise ValueError("Checkpoint exceeds local size limit")
        chunks = []
        remaining = MAX_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_BYTES or len(raw) != info.st_size:
            raise ValueError("Checkpoint size changed during read")
        return raw
    finally:
        os.close(fd)


@contextmanager
def _writer(directory):
    fd = os.open(".writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                 0o600, dir_fd=directory)
    try:
        _regular(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Concurrent checkpoint writer refused") from None
        yield
    finally:
        os.close(fd)


def save_checkpoint(root, entry, *, trusted_issuers=None):
    with publication_guard(trusted_issuers):
        return _save_checkpoint(root, entry, trusted_issuers=trusted_issuers)


def _save_checkpoint(root, entry, *, trusted_issuers=None):
    # Complete validation BEFORE any filesystem mutation. Detach caller data.
    entry = validate_cache(entry, trusted_issuers=trusted_issuers)
    request_hash, entry_hash = digest(entry["request"]), digest(entry)
    identity = request_hash + "." + entry_hash
    wrapped = {"format": FORMAT, "request_sha256": request_hash, "entry_sha256": entry_hash, "entry": entry}
    raw = canonical_json(wrapped).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("Checkpoint exceeds local size limit")
    name = identity + ".json"
    with _directory(root) as directory, _writer(directory):
        try:
            existing = _read(directory, name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != raw:
                raise ValueError("Existing checkpoint conflicts with immutable content")
            return identity
        temporary = ".pending-" + secrets.token_hex(16)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory)
        try:
            try:
                view = memoryview(raw)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError("Checkpoint write incomplete")
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            # Private directory + cooperative exclusive writer lock: the name
            # was checked above. Rename publishes a complete single-link file,
            # including if the process dies immediately after publication.
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    return identity


def load_checkpoint(root, request, identity, *, trusted_issuers=None):
    request = _request(request)
    if not isinstance(identity, str) or ID.fullmatch(identity) is None or identity.split(".")[0] != digest(request):
        raise ValueError("Explicit checkpoint identity of this exact request required")
    with _directory(root) as directory:
        data = copy_metadata(strict_json_loads(_read(directory, identity + ".json")))
    if not isinstance(data, dict) or set(data) != {"format", "request_sha256", "entry_sha256", "entry"}:
        raise ValueError("Versioned checkpoint required")
    if (data["format"] != FORMAT or data["request_sha256"] != digest(request)
            or data["entry_sha256"] != digest(data["entry"])
            or identity != data["request_sha256"] + "." + data["entry_sha256"]):
        raise ValueError("Checkpoint integrity mismatch")
    entry = validate_cache(data["entry"], trusted_issuers=trusted_issuers)
    if entry["request"] != request:
        raise ValueError("Checkpoint belongs to another request")
    return entry
