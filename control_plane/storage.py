"""Private local POSIX layout, explicit migration and transaction boundary."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import os
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import Problem, canonical, decode_json, new_id, sha256


@dataclass(frozen=True)
class Settings:
    max_file_bytes: int = 1_048_576
    quota_bytes: int = 16_777_216
    attempt_seconds: int = 60

    def __post_init__(self):
        if (any(type(x) is not int or x <= 0 for x in asdict(self).values())
                or self.max_file_bytes > 1_048_576 or self.quota_bytes > 1_073_741_824
                or self.attempt_seconds > 3600):
            raise Problem("invalid_settings")


def private_directory(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise Problem("unsafe_data_directory")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise Problem("unsafe_data_directory")
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) & 0o077):
        raise Problem("private_data_directory_required")
    return path


def read_private(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > limit):
            raise Problem("unsafe_local_file", 500)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit or len(data) != info.st_size:
            raise Problem("invalid_local_file", 500)
        return data
    finally:
        os.close(fd)


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


class Store:
    def __init__(self, root, *, settings=None):
        root = Path(root)
        code_root = Path(__file__).resolve().parents[1]
        if not root.is_absolute() or ".." in root.parts or root.resolve().is_relative_to(code_root):
            raise Problem("data_must_be_outside_source")
        if not root.exists():
            root.mkdir(mode=0o700)
        self.root = private_directory(root)
        marker = root / "config" / "installation.json"
        if not marker.exists():
            if any(root.iterdir()):
                raise Problem("refusing_unrecognized_directory")
            for name in ("app", "objects", "staging", "logs", "config", "secrets"):
                (root / name).mkdir(mode=0o700)
            chosen = Settings() if settings is None else settings
            write_new(root / "config" / "settings.json", canonical(asdict(chosen)).encode())
            for role in ("admin", "worker"):
                write_new(root / "secrets" / (role + ".token"), secrets.token_urlsafe(32).encode() + b"\n")
            write_new(marker, canonical({"format": "pepeuch.control-plane-installation/v1"}).encode())
        for name in ("app", "objects", "staging", "logs", "config", "secrets"):
            private_directory(root / name)
        if decode_json(read_private(marker, 1024)) != {"format": "pepeuch.control-plane-installation/v1"}:
            raise Problem("unknown_installation")
        self.settings = Settings(**decode_json(read_private(root / "config" / "settings.json", 1024)))
        if settings is not None and settings != self.settings:
            raise Problem("settings_mismatch")
        self.lock = os.open(root / "app" / "backend.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.lock)
            self.lock = None
            raise Problem("backend_already_running", 409) from None
        try:
            self.path = root / "app" / "index.sqlite3"
            if not self.path.exists():
                write_new(self.path, b"")
            read_private(self.path, 1_073_741_824)
            self._migrate()
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    @contextmanager
    def transaction(self):
        con = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _migrate(self):
        raw = (Path(__file__).parent / "migrations" / "0001.sql").read_bytes()
        checksum = sha256(raw)
        with self.transaction() as con:
            exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
            if exists:
                rows = con.execute("SELECT version,sha256 FROM schema_migrations").fetchall()
                if [tuple(row) for row in rows] != [(1, checksum)]:
                    raise Problem("unsupported_storage_version", 500)
                return
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                raise Problem("refusing_foreign_database", 500)
            for statement in raw.decode().split(";"):
                if statement.strip():
                    con.execute(statement)
            con.execute("INSERT INTO schema_migrations VALUES (?,?)", (1, checksum))
            con.execute("INSERT INTO workspaces VALUES (?,?,?)", (new_id("w"), "local-admin", "local-project"))
