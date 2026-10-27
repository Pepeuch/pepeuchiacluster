"""Independent manual CPU worker. No backend data directory is accepted."""

import argparse
from pathlib import Path
import signal
import sys
import threading

from control_plane.contracts import Problem, canonical, decode_json
from control_plane.worker_client import LocalClient
from .contracts import configuration
from .executor import CPUTextDigest
from .isolation import inspect, require_isolation
from . import private_io
from .runner import IndependentRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "inspect", "run"):
        sub = commands.add_parser(name)
        sub.add_argument("--worker-dir", type=Path, required=True)
        if name == "init":
            sub.add_argument("--configuration-file", type=Path, required=True, help="Public configuration, never a credential")
        if name == "run":
            sub.add_argument("--credential-file", type=Path, help="Private file, otherwise worker-dir/credential")
            sub.add_argument("--application-test", action="store_true", help="Explicit functional test WITHOUT verified OS isolation")
            sub.add_argument("--recover", action="store_true", help="Recover pending claim/publication or interrupt; never recompute")
    args = parser.parse_args()
    try:
        if args.command == "init":
            raw = private_io.configuration_input(args.configuration_file)
            data = configuration(decode_json(raw))
            root = private_io.absolute(args.worker_dir)
            # Existing roots are never repurposed or repaired silently.
            root.mkdir(mode=0o700)
            private_io.directory(root)
            private_io.create(root / "worker.json", canonical(data).encode())
            print("Configuration CPU créée ; credential à fournir séparément. OS : NOT VERIFIED.")
            return 0
        root = private_io.directory(args.worker_dir)
        data = configuration(decode_json(private_io.read(root / "worker.json", 16384)))
        if args.command == "inspect":
            print(canonical(inspect(data)))
            return 0
        if not args.application_test:
            require_isolation(data)  # Before credential access or any backend connection.
        credential = private_io.credential(root / "credential" if args.credential_file is None else args.credential_file)
        stop = threading.Event()
        def interrupt(_number, _frame):
            stop.set()
        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        runner = IndependentRunner(root, data, credential, LocalClient(data["backend_url"], credential),
                                   CPUTextDigest(data["limits"], stop=stop))
        outcome = runner.run_once(recover=args.recover)
        print("Worker CPU : " + outcome + "; aucune inférence ; OS : NOT VERIFIED.")
        return 0
    except (Problem, OSError, ValueError) as exc:
        # Neither exception text, credential, objective, nor arbitrary paths are logged.
        code = exc.code if isinstance(exc, Problem) else "worker_operation_failed"
        print("Worker refusé : " + code, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
