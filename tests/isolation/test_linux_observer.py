from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_plane.contracts import Problem
from pepeuch_worker.linux_observer import cgroup_path, collect, mountinfo, process_start, process_status
from fixtures import configuration


class LinuxObserver(unittest.TestCase):
    def test_01_cgroup_v1_mixed_traversal_and_malformed_mounts_refused(self):
        for raw in ("1:cpu:/x", "0::/x\n1:cpu:/x", "0::/../../escape", "missing"):
            with self.assertRaises(Problem):
                cgroup_path(raw)
        with self.assertRaises(Problem):
            mountinfo("not a mount record")

    def test_02_missing_duplicate_status_fields_refused(self):
        with self.assertRaises(Problem):
            process_status("Uid:\t1001 1001 1001 1001\n")
        with self.assertRaises(Problem):
            process_status("Uid:\t1 1 1 1\nUid:\t1 1 1 1\n")

    def test_03_pid_start_comm_with_spaces_and_parentheses(self):
        raw = "42 (name ) extra) " + " ".join(["S"] + ["0"] * 18 + ["12345"])
        self.assertEqual(process_start(raw), 12345)

    def test_04_mounts_unescape_and_redact_unknown_sensitive_options(self):
        rows = mountinfo("1 0 0:1 / /opt/a\\040b ro,nosuid - ext4 /dev/a rw,password=do-not-export\n")
        self.assertEqual(rows[0]["mountpoint"], "/opt/a b")
        self.assertNotIn("do-not-export", str(rows))
        self.assertEqual(rows[0]["options"], ["nosuid", "ro"])

    def test_05_fixture_collection_binds_process_cgroup_and_boot_without_authority(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b531-proc-fixture-") as temporary:
            root = Path(temporary)
            proc, cgroups = root / "proc", root / "cgroup"
            target = proc / "42"
            (target / "ns").mkdir(parents=True)
            (target / "fd").mkdir()
            stat = "42 (a ) b) " + " ".join(["S"] + ["0"] * 18 + ["123"])
            (target / "stat").write_text(stat)
            (target / "status").write_text("Uid:\t1001 1001 1001 1001\nGid:\t1001 1001 1001 1001\nGroups:\t1001\nNoNewPrivs:\t1\nSeccomp:\t2\n" + "".join(name + ":\t00000000\n" for name in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")))
            (target / "cgroup").write_text("0::/test.service\n")
            (target / "mountinfo").write_text("1 0 0:1 / / ro - ext4 /dev/a rw\n")
            for name in ("user", "mnt", "net", "pid", "cgroup", "time"):
                (target / "ns" / name).symlink_to(name + ":[42]")
            (proc / "sys/kernel/random").mkdir(parents=True)
            (proc / "sys/kernel/random/boot_id").write_text("synthetic-boot")
            (proc / "sys/kernel/osrelease").write_text("synthetic-kernel")
            (cgroups / "test.service").mkdir(parents=True)
            (cgroups / "cgroup.controllers").write_text("cpu memory pids")
            for name, value in (("cpu.max", "50000 100000"), ("memory.max", "134217728"), ("memory.swap.max", "0"), ("pids.max", "8")):
                (cgroups / "test.service" / name).write_text(value)
            result = collect(configuration(), pid=42, proc=proc, cgroups=cgroups, clock=lambda: 100)
            self.assertEqual(result["unavailable"], [])
            self.assertTrue(result["stable"])
            self.assertTrue(result["synthetic"])
            self.assertEqual(result["process"]["start_ticks"], 123)
            self.assertEqual(result["process"]["cgroup"], "/test.service")
            self.assertEqual(result["applied"]["pids.max"], "8")
            (target / "stat").write_text("gone")
            self.assertFalse(collect(configuration(), pid=42, proc=proc, cgroups=cgroups)["stable"])

    def test_06_unavailable_process_does_not_fall_back_or_succeed(self):
        with tempfile.TemporaryDirectory(prefix="pepeuch-b531-no-proc-") as temporary:
            result = collect(configuration(), pid=42, proc=Path(temporary), cgroups=Path(temporary))
        self.assertFalse(result["stable"])
        self.assertIn("process_status", result["unavailable"])
        self.assertIsNone(result["process"]["cgroup"])
