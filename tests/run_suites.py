#!/usr/bin/env python3
"""Run each automated suite in its own process; never execute a DB benchmark."""

import argparse
import os
from pathlib import Path
import subprocess
import sys


SUITES = ("discovery", "control_plane", "infrastructure", "isolation", "worker")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, action="append")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    failed = False
    for suite in args.suite or SUITES:
        command = [sys.executable, "-m", "unittest"]
        if suite == "discovery":
            command += ["tests.discovery"]
        else:
            command += ["discover", "-s", f"tests/{suite}", "-p", "test_*.py"]
        command += ["-q" if args.quiet else "-v"]
        print(f"Running {suite}", flush=True)
        result = subprocess.run(command, cwd=root, env=env)
        failed = failed or result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
