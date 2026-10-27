"""Explicit OFFLINE private directory backups, no archives, no deletion.

Hashes detect corruption, not malicious replacement of an entire backup.
Restores never reuse credentials. Local trusted POSIX storage only.
"""

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import secrets
import sqlite3

from .contracts import Problem, canonical, decode_json, fields, identifier, sha256
from .storage import Settings, private_directory, read_private, write_new
from .workspace import file_name


FORMAT = "pepeuch.control-plane-backup/v1"
MAX_INDEX = 256 * 1024 * 1024
MAX_MANIFEST = 4 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}")


def migrations():
    return [(int(path.stem), path.read_bytes()) for path in sorted((Path(__file__).parent / "migrations").glob("*.sql"))]


def verify_index(con):
    """Reject unknown/modified schemas, FK failures and invalid file references."""
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA trusted_schema=OFF")
    if [r[0] for r in con.execute("PRAGMA integrity_check")] != ["ok"] or con.execute("PRAGMA foreign_key_check").fetchone():
        raise Problem("invalid_backup_index")
    history = [tuple(row) for row in con.execute("SELECT version,sha256 FROM schema_migrations ORDER BY version")]
    known = migrations()
    if not history or history != [(version, sha256(raw)) for version, raw in known[:len(history)]]:
        raise Problem("unsupported_storage_version")
    expected = sqlite3.connect(":memory:")
    try:
        for _, raw in known[:len(history)]:
            for statement in raw.decode().split(";"):
                if statement.strip():
                    expected.execute(statement)
        query = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"
        if [tuple(row) for row in con.execute(query)] != expected.execute(query).fetchall():
            raise Problem("invalid_backup_schema")
    finally:
        expected.close()
    if con.execute("SELECT 1 FROM files f LEFT JOIN versions v ON v.file_id=f.id GROUP BY f.id HAVING MIN(v.number) IS NULL OR MIN(v.number)<>1 OR MAX(v.number)<>COUNT(*)").fetchone():
        raise Problem("invalid_backup_references")
    if con.execute("SELECT 1 FROM missions m WHERE m.state='completed' AND NOT EXISTS(SELECT 1 FROM results r JOIN attempts a ON a.id=r.attempt_id JOIN tasks t ON t.id=a.task_id WHERE t.mission_id=m.id)").fetchone():
        raise Problem("invalid_backup_references")
    if con.execute("SELECT 1 FROM results r JOIN versions v ON v.id=r.version_id JOIN attempts a ON a.id=r.attempt_id JOIN tasks t ON t.id=a.task_id JOIN missions m ON m.id=t.mission_id JOIN files f ON f.id=v.file_id WHERE v.attempt_id IS NOT a.id OR v.mission_id IS NOT m.id OR f.workspace_id<>m.workspace_id OR a.state<>'completed' OR m.state<>'completed'").fetchone():
        raise Problem("invalid_backup_references")
    for table in ("missions", "tasks", "attempts", "workspaces", "files", "versions", "results", "events"):
        for row in con.execute(f"SELECT id FROM {table}"):
            identifier(row[0])
    for row in con.execute("SELECT name FROM files"):
        file_name(row[0])
    objects = {}
    for row in con.execute("SELECT sha256,size FROM versions"):
        digest, size = row
        if (not isinstance(digest, str) or HEX.fullmatch(digest) is None
                or type(size) is not int or not 0 <= size <= 1_048_576
                or digest in objects and objects[digest] != size):
            raise Problem("invalid_backup_references")
        objects[digest] = size
    return objects


@contextmanager
def readonly_index(path):
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        yield con
    finally:
        con.close()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def offline(root):
    root = private_directory(root)
    private_directory(root / "app")
    read_private(root / "app/backend.lock", 1024)
    fd = os.open(root / "app/backend.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Problem("stop_backend_before_backup", 409) from None
        if any(os.path.lexists(root / ("app/index.sqlite3" + suffix)) for suffix in ("-journal", "-wal", "-shm")):
            raise Problem("offline_database_recovery_required")
        yield root
    finally:
        os.close(fd)


def new_directory(path):
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts
            or path.resolve().is_relative_to(Path(__file__).resolve().parents[1])):
        raise Problem("unsafe_backup_destination")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise Problem("unsafe_backup_destination")
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        raise Problem("destination_already_exists", 409) from None
    return private_directory(path)


def configurations(root):
    marker = read_private(root / "config/installation.json", 1024)
    if decode_json(marker) != {"format": "pepeuch.control-plane-installation/v1"}:
        raise Problem("unknown_installation")
    settings = read_private(root / "config/settings.json", 1024)
    data = decode_json(settings)
    fields(data, ("max_file_bytes", "quota_bytes", "attempt_seconds"))
    Settings(**data)
    return {"config/installation.json": marker, "config/settings.json": settings}


def create_backup(root, destination):
    with offline(Path(root)) as root:
        if Path(destination).resolve().is_relative_to(root.resolve()):
            raise Problem("backup_must_be_outside_source")
        for part in ("objects", "config"):
            private_directory(root / part)
        configs = configurations(root)
        read_private(root / "app/index.sqlite3", MAX_INDEX)
        with readonly_index(root / "app/index.sqlite3") as con:
            objects = verify_index(con)
        paths = ["app/index.sqlite3", *configs, *("objects/" + digest for digest in sorted(objects))]
        destination = new_directory(destination)
        for part in ("app", "config", "objects"):
            (destination / part).mkdir(mode=0o700)
        records = []
        for name in paths:
            raw = read_private(root / name, MAX_INDEX if name == "app/index.sqlite3" else 1_048_576)
            if name.startswith("objects/") and (sha256(raw) != name[8:] or len(raw) != objects[name[8:]]):
                raise Problem("source_object_corrupted")
            write_new(destination / name, raw)
            records.append({"path": name, "size": len(raw), "sha256": sha256(raw)})
        manifest = {"format": FORMAT, "credentials": "excluded_restore_rekeys", "files": records}
        for part in ("app", "config", "objects"):
            sync_directory(destination / part)
        # Commit marker LAST; an interrupted copy is never an accepted backup.
        write_new(destination / "manifest.json", canonical(manifest).encode())
        sync_directory(destination)
        inspect_backup(destination)
        return {"format": FORMAT, "file_count": len(records), "credentials_included": False}


def inspect_backup(root):
    try:
        root = private_directory(root)
        if set(p.name for p in root.iterdir()) != {"manifest.json", "app", "config", "objects"}:
            raise Problem("invalid_backup_layout")
        for name in ("app", "config", "objects"):
            private_directory(root / name)
        data = decode_json(read_private(root / "manifest.json", MAX_MANIFEST))
        fields(data, ("format", "credentials", "files"))
        if data["format"] != FORMAT or data["credentials"] != "excluded_restore_rekeys" or not isinstance(data["files"], list) or not 3 <= len(data["files"]) <= 10003:
            raise Problem("invalid_backup_manifest")
        paths = {}
        total = 0
        for entry in data["files"]:
            fields(entry, ("path", "size", "sha256"))
            name = entry["path"]
            if (not isinstance(name, str) or (name not in {"app/index.sqlite3", "config/settings.json", "config/installation.json"}
                    and re.fullmatch(r"objects/[0-9a-f]{64}", name) is None) or name in paths
                    or type(entry["size"]) is not int or entry["size"] < 0):
                raise Problem("invalid_backup_manifest")
            raw = read_private(root / name, MAX_INDEX if name == "app/index.sqlite3" else 1_048_576)
            if len(raw) != entry["size"] or sha256(raw) != entry["sha256"]:
                raise Problem("backup_integrity_mismatch")
            paths[name] = entry
            total += len(raw)
        if total > 2_147_483_648:
            raise Problem("backup_too_large")
        actual = {str(p.relative_to(root)) for name in ("app", "config", "objects") for p in (root / name).iterdir()}
        if actual != set(paths):
            raise Problem("invalid_backup_layout")
        configurations(root)
        with readonly_index(root / "app/index.sqlite3") as con:
            objects = verify_index(con)
        if {name for name in paths if name.startswith("objects/")} != {"objects/" + value for value in objects}:
            raise Problem("invalid_backup_references")
        for digest, size in objects.items():
            if paths["objects/" + digest]["sha256"] != digest or paths["objects/" + digest]["size"] != size:
                raise Problem("invalid_backup_references")
        return data
    except (OSError, ValueError, sqlite3.Error):
        raise Problem("invalid_backup") from None


def restore_backup(backup, destination):
    backup = Path(backup)
    manifest = inspect_backup(backup)
    destination = new_directory(destination)
    for part in ("app", "objects", "staging", "logs", "config", "secrets"):
        (destination / part).mkdir(mode=0o700)
    marker = None
    for entry in manifest["files"]:
        raw = read_private(backup / entry["path"], MAX_INDEX if entry["path"] == "app/index.sqlite3" else 1_048_576)
        if len(raw) != entry["size"] or sha256(raw) != entry["sha256"]:
            raise Problem("backup_changed_during_restore")
        if entry["path"] == "config/installation.json":
            marker = raw
        else:
            write_new(destination / entry["path"], raw)
    with readonly_index(destination / "app/index.sqlite3") as con:
        verify_index(con)
    # Registry introduced by B5.2c: never reactivate identities copied in a backup.
    with sqlite3.connect(destination / "app/index.sqlite3") as con:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='worker_identities'").fetchone():
            con.execute("UPDATE worker_identities SET status='revoked',credential_epoch=credential_epoch+1")
    for role in ("admin", "worker"):
        write_new(destination / "secrets" / (role + ".token"), secrets.token_urlsafe(32).encode() + b"\n")
    write_new(destination / "app/backend.lock", b"")
    for part in ("app", "objects", "staging", "logs", "config", "secrets"):
        sync_directory(destination / part)
    if marker is None:
        raise Problem("incomplete_restore")
    # Until this marker exists, Store refuses this nonempty, unfinished directory.
    write_new(destination / "config/installation.json", marker)
    sync_directory(destination / "config")
    sync_directory(destination)
    return {"restored": True, "credentials": "new_local_credentials", "workers": "explicit_reenrollment_required"}
