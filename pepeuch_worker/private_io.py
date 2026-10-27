"""Worker-owned files only. No backend store, SQLite or administrative secrets."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from control_plane.contracts import Problem, canonical, decode_json


def absolute(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Problem("unsafe_worker_path")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise Problem("unsafe_worker_path")
    return path


def directory(path):
    path = absolute(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise Problem("worker_directory_not_private")
    return path


def read(path, maximum):
    path = absolute(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) not in (0o400, 0o600) or info.st_size > maximum):
            raise Problem("worker_file_not_private")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise Problem("worker_file_too_large")
        return raw
    finally:
        os.close(fd)


def credential(path):
    raw = read(path, 128)
    if re.fullmatch(rb"[A-Za-z0-9_-]{43}\n?", raw) is None:
        raise Problem("invalid_worker_credential")
    return raw.rstrip(b"\n").decode("ascii")


def configuration_input(path):
    fd = os.open(absolute(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise Problem("invalid_worker_configuration_file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise Problem("worker_configuration_too_large")
        return raw
    finally:
        os.close(fd)


def sync(directory_path):
    fd = os.open(directory_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create(path, raw):
    directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    sync(path.parent)


def save(root, data):
    """Atomic durable journal. Replacement never follows links or overwrites others."""
    root = directory(root)
    target = root / "run.json"
    if target.exists() or target.is_symlink():
        read(target, 262144)
    temporary = root / (".journal-" + uuid4().hex)
    try:
        create(temporary, canonical(data).encode())
        os.replace(temporary, target)
        sync(root)
    finally:
        temporary.unlink(missing_ok=True)


def load(root):
    path = directory(root) / "run.json"
    return None if not path.exists() and not path.is_symlink() else decode_json(read(path, 262144))


@contextmanager
def locked(root):
    root = directory(root)
    path = root / "run.lock"
    if not path.exists() and not path.is_symlink():
        try:
            create(path, b"")
        except FileExistsError:
            pass
    read(path, 1)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Problem("worker_already_running", 409) from None
        yield
    finally:
        os.close(fd)
