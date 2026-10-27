"""Explicit one-shot ROOT diagnostic pilot, never started by tests or worker.

Creates a new private /run directory and a short-lived socket only after a future
operator authorization. Currently DENIES every launch: independent OS attestation
is not implemented or qualified. This is NOT an installation or activation tool.
"""

import argparse
import os
from pathlib import Path
import re
import socket
import stat
import sys

from control_plane.contracts import Problem, decode_json
from pepeuch_worker.contracts import configuration
from pepeuch_worker.private_io import configuration_input, opened_directory
from pepeuch_worker.verification import digest, policy
from pepeuch_worker.verifier import serve_diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--configuration-file", required=True, type=Path)
    parser.add_argument("--policy-file", required=True, type=Path)
    parser.add_argument("--authorized-disposable-pilot", action="store_true")
    args = parser.parse_args()
    try:
        if not args.authorized_disposable_pilot or os.geteuid() != 0 or os.getegid() != 0:
            raise Problem("authorized_root_pilot_required")
        if re.fullmatch(r"[0-9a-f]{32}", args.run_id) is None:
            raise Problem("invalid_pilot_run_id")
        config = configuration(decode_json(configuration_input(args.configuration_file)))
        requested = policy(decode_json(configuration_input(args.policy_file)))
        if requested["configuration_sha256"] != digest(config):
            raise Problem("configuration_changed")
        root = Path("/run") / ("pepeuch-b531-verifier-" + args.run_id)
        with opened_directory(root.parent) as parent:
            os.mkdir(root.name, 0o700, dir_fd=parent)  # Never reuse an existing path.
        initial = root.lstat()
        root_identity = initial.st_dev, initial.st_ino
        endpoint = root / "verifier.sock"
        identity = None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                listener.bind(str(endpoint))
                os.chmod(endpoint, 0o600)
                info = endpoint.lstat()
                identity = info.st_dev, info.st_ino
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
                listener.listen(1)
                listener.settimeout(20)
                print("Contrôleur diagnostic temporaire prêt ; décision attendue : deny.", flush=True)
                connection, _ = listener.accept()
                with connection:
                    serve_diagnostic(connection, config, requested)
        finally:
            try:
                current = endpoint.lstat()
                if identity == (current.st_dev, current.st_ino) and stat.S_ISSOCK(current.st_mode):
                    endpoint.unlink()
            except FileNotFoundError:
                pass
            # No recursive cleanup. Preserve unexpected files for review.
            try:
                current = root.lstat()
                if (current.st_dev, current.st_ino) == root_identity:
                    root.rmdir()
            except OSError:
                pass
        return 2  # Diagnostic denial is expected, never a validated deployment.
    except (Problem, OSError, ValueError):
        print("Contrôleur refusé : NOT VERIFIED", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
