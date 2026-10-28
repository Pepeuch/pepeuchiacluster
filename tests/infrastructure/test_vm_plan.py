"""Offline only: host commands are stubs and all writes stay in private /tmp."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "infrastructure/proxmox/create-ai-vm.sh"
spec = importlib.util.spec_from_file_location("vm_plan", SCRIPT.with_name("vm_plan.py"))
vm_plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm_plan)


class Plan(unittest.TestCase):
    def test_plan_is_unprivileged_no_commands_key_reads_or_network(self):
        env = {**os.environ, "VMID": "9500", "VMNAME": "pepeuch-test-9500", "SSH_KEY_FILE": "/not-read/private-key"}
        result = subprocess.run(["bash", str(SCRIPT), "--plan"], env=env, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data["executed"])
        self.assertFalse(data["starts_vm"])
        self.assertFalse(data["gpu_passthrough"])
        self.assertEqual(data["status"], "PARTIAL")

    def test_production_vm150_invalid_limits_or_injection_refused(self):
        for change in ({"VMID": "150"}, {"VMID": "0150"}, {"VMID": "-1"}, {"MEMORY_MB": "0"}, {"CORES": "9999"},
                       {"CI_USER": "user; unexpected"}, {"VMNAME": "x\nruncmd:"}, {"STORAGE": "--flag"},
                       {"IMAGE_FILE": "/tmp/../outside"}, {"IMAGE_URL": "http://cloud.debian.org/image"},
                       {"IMAGE_URL": "https://user:private@example.test/image"}, {"IMAGE_SHA256": "invalid"}):
            with self.assertRaises(ValueError):
                vm_plan.build_plan(change)

    def test_plan_does_not_emit_unrelated_environment_secrets(self):
        data = vm_plan.build_plan({"UNRELATED_PRIVATE_VALUE": "synthetic-do-not-export"})
        self.assertNotIn("synthetic-do-not-export", json.dumps(data))

    def test_file_metadata_refuses_links_and_writable_shared_parents(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-vm-plan-") as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir(mode=0o700)
            (root / "link").symlink_to(real, target_is_directory=True)
            for parent in (root / "link", root / "shared"):
                if not parent.exists():
                    parent.mkdir(mode=0o777)
                    parent.chmod(0o777)
                data = vm_plan.build_plan({"IMAGE_FILE": str(parent / "image"), "SNIPPET_DIR": str(real)})
                with self.assertRaises(ValueError):
                    vm_plan.check_paths(data)


STUB = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as output:
    output.write(json.dumps([name, *args]) + "\n")
if name == "id":
    print("0")  # Simulated identity only: actual process remains the ordinary UID.
elif name == "pvesm":
    print("Name Type Status")
    print("local dir active")
    print("local-lvm lvmthin active")
elif name == "qm":
    if args[0] == "status":
        sys.exit(0 if os.environ.get("EXISTING_VM") else 1)
    if args[0] == "config":
        print("efidisk0: local-lvm:vm-9500-disk-0")
        print("unused0: local-lvm:vm-9500-disk-1")
        if os.environ.get("AMBIGUOUS_DISKS"):
            print("unused1: local-lvm:vm-9500-disk-2")
elif name == "wget":
    path = pathlib.Path(args[args.index("-O") + 1])
    path.write_bytes(b"synthetic-cloud-image")
    if os.environ.get("DOWNLOAD_FAIL"):
        sys.exit(7)
'''


class Script(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pepeuch-vm-stub-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        commands = self.root / "bin"
        commands.mkdir(mode=0o700)
        for name in ("id", "qm", "pvesm", "wget"):
            path = commands / name
            path.write_text(STUB)
            path.chmod(0o700)
        self.image = self.root / "image.qcow2"
        self.snippets = self.root / "snippets"
        self.snippets.mkdir(mode=0o700)
        self.env = {**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"],
                    "VMID": "9500", "VMNAME": "pepeuch-test-9500", "CI_USER": "test-user", "MEMORY_MB": "2048", "CORES": "2", "DISK_GB": "16",
                    "IMAGE_FILE": str(self.image), "SNIPPET_DIR": str(self.snippets), "SSH_KEY_FILE": str(self.root / "no-key"),
                    "STUB_LOG": str(self.root / "calls.jsonl"), "IMAGE_SHA256": hashlib.sha256(b"synthetic-cloud-image").hexdigest()}
        for name in ("EXISTING_VM", "DOWNLOAD_FAIL", "AMBIGUOUS_DISKS"):
            self.env.pop(name, None)

    def run_script(self, **changes):
        return subprocess.run(["bash", str(SCRIPT)], env={**self.env, **changes}, capture_output=True, timeout=10)

    def calls(self):
        path = self.root / "calls.jsonl"
        return [] if not path.exists() else [json.loads(line) for line in path.read_text().splitlines()]

    def test_protected_vmid_refuses_before_any_host_command_or_write(self):
        result = self.run_script(VMID="150")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.image.exists())

    def test_existing_vm_and_existing_snippet_are_preserved(self):
        self.assertNotEqual(self.run_script(EXISTING_VM="1").returncode, 0)
        self.assertFalse(self.image.exists())
        target = self.snippets / "pepeuch-test-9500-user-data.yaml"
        target.write_bytes(b"preserve existing user data")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(target.read_bytes(), b"preserve existing user data")

    def test_download_failure_does_not_publish_partial_image_or_create_vm(self):
        self.assertNotEqual(self.run_script(DOWNLOAD_FAIL="1").returncode, 0)
        self.assertFalse(self.image.exists())
        self.assertTrue(any(c[0] == "wget" for c in self.calls()))
        self.assertFalse(any(c[:2] == ["qm", "create"] for c in self.calls()))
        self.assertEqual(list(self.root.glob("*.pending.*")), [])

    def test_wrong_existing_image_hash_and_symlink_are_refused(self):
        self.image.write_bytes(b"existing opaque image must survive")
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.image.read_bytes(), b"existing opaque image must survive")
        self.image.unlink()
        target = self.root / "preserved"
        target.write_bytes(b"preserved")
        self.image.symlink_to(target)
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(target.read_bytes(), b"preserved")

    def test_ambiguous_imported_disk_refuses_attach_without_automatic_destroy(self):
        self.assertNotEqual(self.run_script(AMBIGUOUS_DISKS="1").returncode, 0)
        self.assertTrue(any(c[:2] == ["qm", "importdisk"] for c in self.calls()))
        self.assertFalse(any(c[:2] == ["qm", "destroy"] or "--scsi0" in c for c in self.calls()))

    def test_guest_userdata_substitutes_user_and_uses_posix_directories(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = (self.snippets / "pepeuch-test-9500-user-data.yaml").read_text()
        self.assertIn("usermod -aG docker test-user", text)
        self.assertNotIn("${CI_USER}", text)
        self.assertNotIn("__PEPEUCH_CI_USER__", text)
        self.assertNotIn("/opt/pepeuch-ai/{", text)
        self.assertTrue(any("--scsi0" in c and "local-lvm:vm-9500-disk-1,discard=on,ssd=1,iothread=1" in c for c in self.calls()))
        self.assertFalse(any(c[:2] == ["qm", "start"] or "--hostpci0" in c for c in self.calls()))

    def test_invalid_user_input_never_reaches_cloudinit(self):
        result = self.run_script(CI_USER="bad\n  runcmd: arbitrary")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_private_key_material_is_not_accepted_or_logged_as_public_key(self):
        path = self.root / "private.synthetic"
        path.write_text("synthetic-private-value\n")
        result = self.run_script(SSH_KEY_FILE=str(path))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b"synthetic-private-value", result.stdout + result.stderr)
        self.assertFalse(any(c[:2] == ["qm", "create"] for c in self.calls()))
