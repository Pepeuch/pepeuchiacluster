"""Anchored worker-owned I/O. Every component is opened without following links."""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from control_plane.contracts import Problem, canonical, decode_json


DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
JOURNAL_MAX = 262144


def absolute(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Problem("unsafe_worker_path")
    return path


@contextmanager
def opened_directory(path, *, private=False):
    path = absolute(path)
    fd = os.open("/", DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        if private:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise Problem("worker_directory_not_private")
        yield fd
    except OSError as exc:
        if exc.errno in (20, 40):  # ENOTDIR/ELOOP, including intermediate links.
            raise Problem("unsafe_worker_path") from None
        raise
    finally:
        os.close(fd)


def directory(path):
    with opened_directory(path, private=True):
        return absolute(path)


def initialize_directory(path):
    path = absolute(path)
    with opened_directory(path.parent) as parent:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        os.fsync(parent)
    return directory(path)


def _validated_file(fd, maximum, *, private=True):
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum
            or private and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) not in (0o400, 0o600))):
        raise Problem("worker_file_not_private" if private else "invalid_worker_configuration_file")
    return info


def _read_at(parent, name, maximum, *, private=True):
    try:
        fd = os.open(name, FILE_FLAGS, dir_fd=parent)
    except OSError as exc:
        if exc.errno == 40:
            raise Problem("unsafe_worker_path") from None
        raise
    try:
        _validated_file(fd, maximum, private=private)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(maximum + 1)
        if len(raw) > maximum:
            raise Problem("worker_file_too_large")
        return raw
    finally:
        os.close(fd)


def read(path, maximum):
    path = absolute(path)
    with opened_directory(path.parent) as parent:
        return _read_at(parent, path.name, maximum)


def configuration_input(path):
    path = absolute(path)
    with opened_directory(path.parent) as parent:
        return _read_at(parent, path.name, 16384, private=False)


def credential(path):
    raw = read(path, 128)
    if re.fullmatch(rb"[A-Za-z0-9_-]{43}\n?", raw) is None:
        raise Problem("invalid_worker_credential")
    return raw.rstrip(b"\n").decode("ascii")


def sync(directory_path):
    with opened_directory(directory_path) as fd:
        os.fsync(fd)


def _create_at(parent, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
        info = os.fstat(fd)
        return info.st_dev, info.st_ino
    finally:
        os.close(fd)


def create(path, raw):
    path = absolute(path)
    with opened_directory(path.parent, private=True) as parent:
        _create_at(parent, path.name, raw)
        os.fsync(parent)


def save(root, data):
    raw = canonical(data).encode()
    if len(raw) > JOURNAL_MAX:
        raise Problem("worker_file_too_large")
    with opened_directory(root, private=True) as parent:
        try:
            _read_at(parent, "run.json", JOURNAL_MAX)
        except FileNotFoundError:
            pass
        name = ".journal-" + uuid4().hex
        identity = None
        try:
            identity = _create_at(parent, name, raw)
            os.replace(name, "run.json", src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            # Never remove a colliding or replaced file that we did not create.
            if identity is not None:
                try:
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if (info.st_dev, info.st_ino) == identity:
                        os.unlink(name, dir_fd=parent)
                except FileNotFoundError:
                    pass


def load(root):
    with opened_directory(root, private=True) as parent:
        try:
            return decode_json(_read_at(parent, "run.json", JOURNAL_MAX))
        except FileNotFoundError:
            return None


@contextmanager
def locked(root):
    with opened_directory(root, private=True) as parent:
        try:
            fd = os.open("run.lock", FILE_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            try:
                _create_at(parent, "run.lock", b"")
            except FileExistsError:
                pass
            fd = os.open("run.lock", FILE_FLAGS, dir_fd=parent)
        try:
            _validated_file(fd, 1)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Problem("worker_already_running", 409) from None
            yield
        finally:
            os.close(fd)
