"""Run with python3 -m control_plane; no installer, GPU or provider account."""

import argparse
from pathlib import Path
import sqlite3
import sys
import threading

from .contracts import Problem
from .http_api import API, LocalServer
from .service import ControlPlane
from .storage import Settings, Store, private_directory, read_private
from .worker_client import LocalClient, WorkerRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "serve", "worker"):
        sub = commands.add_parser(name)
        sub.add_argument("--data-dir", type=Path, required=True, help="Répertoire privé dédié, hors du code")
        if name == "init":
            sub.add_argument("--max-file-bytes", type=int, default=1_048_576)
            sub.add_argument("--quota-bytes", type=int, default=16_777_216)
        if name == "serve":
            sub.add_argument("--port", type=int, default=8765)
        if name == "worker":
            sub.add_argument("--server-url", default="http://127.0.0.1:8765")
            run = sub.add_mutually_exclusive_group()
            run.add_argument("--once", action="store_true", help="Une tâche au maximum (défaut)")
            run.add_argument("--loop", action="store_true", help="Boucle locale explicitement démarrée")
            sub.add_argument("--interactive", action="store_true", help="Attendre Entrée après attribution")
            sub.add_argument("--mode", choices=("success", "fail", "interrupt", "hold"), default="success")
            sub.add_argument("--credential-file", type=Path, help="Fichier privé de credential sous secrets/, sinon worker.token")
    backup_parser = commands.add_parser("backup", help="Sauvegarde privée, backend arrêté")
    backup_parser.add_argument("--data-dir", type=Path, required=True)
    backup_parser.add_argument("--destination", type=Path, required=True)
    restore_parser = commands.add_parser("restore", help="Restaurer dans un répertoire inexistant")
    restore_parser.add_argument("--backup-dir", type=Path, required=True)
    restore_parser.add_argument("--data-dir", type=Path, required=True)
    for name in ("worker-enroll", "worker-rotate"):
        sub = commands.add_parser(name, help="Maintenance locale hors ligne des identités worker")
        sub.add_argument("--data-dir", required=True, type=Path)
        if name == "worker-enroll":
            sub.add_argument("--capability", action="append", default=None)
            sub.add_argument("--max-output-bytes", type=int, default=None)
            sub.add_argument("--lease-seconds", type=int, default=None)
        else:
            sub.add_argument("--worker-id", required=True)
            sub.add_argument("--reactivate", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "init":
            store = Store(args.data_dir, settings=Settings(max_file_bytes=args.max_file_bytes, quota_bytes=args.quota_bytes))
            store.close()
            print("Initialisation locale terminée. Clés privées dans secrets/admin.token et secrets/worker.token.")
        elif args.command == "serve":
            service = ControlPlane(args.data_dir)
            try:
                with LocalServer(API(service), port=args.port) as server:
                    print(f"Pepeuch B5.1 — SIMULATION — http://127.0.0.1:{server.server_port}", flush=True)
                    server.serve_forever()
            finally:
                service.close()
        elif args.command == "worker":
            root = private_directory(args.data_dir)
            private_directory(root / "secrets")
            path = root / "secrets/worker.token" if args.credential_file is None else args.credential_file
            if not path.is_absolute() or path.is_symlink() or not path.resolve().is_relative_to((root / "secrets").resolve()):
                raise Problem("unsafe_credential_path")
            private_directory(path.parent)
            credential = read_private(path, 256).decode("ascii").strip()
            runner = WorkerRunner(LocalClient(args.server_url, credential))
            def pause(_request):
                input("SIMULATION attribuée. Entrée pour continuer (annulation possible dans l'interface) : ")
            while True:
                result = runner.run_once(mode=args.mode, before_execute=pause if args.interactive else None)
                if result != "idle" or not args.loop:
                    print("Worker SIMULÉ : " + result, flush=True)
                if not args.loop:
                    break
                threading.Event().wait(1)
        elif args.command == "backup":
            from .backup import create_backup
            create_backup(args.data_dir, args.destination)
            print("Sauvegarde hors ligne vérifiée. Credentials exclus ; conserver le dossier privé.")
        elif args.command == "restore":
            from .backup import restore_backup
            restore_backup(args.backup_dir, args.data_dir)
            print("Restauration vérifiée. Nouvelles clés locales ; réenrôlement des workers requis.")
        elif args.command in ("worker-enroll", "worker-rotate"):
            import time
            from .contracts import canonical
            from .worker_registry import WorkerRegistry, default_limits
            store = Store(args.data_dir)
            try:
                registry = WorkerRegistry(store, time.time)
                if args.command == "worker-enroll":
                    limits = default_limits(store.settings)
                    if args.max_output_bytes is not None:
                        limits["max_output_bytes"] = args.max_output_bytes
                    if args.lease_seconds is not None:
                        limits["lease_seconds"] = args.lease_seconds
                    result = registry.enroll(capabilities=args.capability, limits=limits)
                else:
                    result = registry.rotate(args.worker_id, reactivate=args.reactivate)
                print(canonical(result))  # Public metadata and relative filename only.
            finally:
                store.close()
        return 0
    except KeyboardInterrupt:
        return 0
    except (Problem, OSError, sqlite3.Error, ValueError) as exc:
        code = exc.code if isinstance(exc, Problem) else "local_operation_failed"
        print("Opération refusée : " + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
