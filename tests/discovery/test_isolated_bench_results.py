"""Offline reproducibility checks against the retained real VM150 measurements."""

import hashlib
import json
import math
from pathlib import Path

from tests.discovery import POC_ROOT
import unittest
from unittest.mock import patch

from confirmed_sql_batches import plan
from isolated_bench_plans import postgres_plan, surreal_plan
from isolated_bench_workload import corpus, expected, pg_statements, surreal_load


ROOT=POC_ROOT/"results/20261028-vm150-isolated-session"


def read(name):
    return json.loads((ROOT/name).read_text())


@unittest.skipUnless(ROOT.is_dir(), "Private VM150 benchmark exports are not distributed with Git")
class RealBenchArtifacts(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection","socket.socket.connect","socket.getaddrinfo","subprocess.Popen"):
            guard=patch(target,side_effect=AssertionError("Retained results checked OFFLINE only"))
            guard.start(); self.addCleanup(guard.stop)

    def test_export_hashes_retained_and_only_new_containers_were_used(self):
        manifest=read("review-manifest.json")
        for name,metadata in manifest["files"].items():
            path=ROOT/name
            self.assertFalse(path.is_symlink())
            raw=path.read_bytes()
            self.assertEqual(len(raw),metadata["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),metadata["sha256"])
        self.assertFalse(manifest["credentials_included"])
        self.assertTrue(manifest["network"]["internal"])
        old={r["id"] for r in read("final/preflight.json")["historical"]}
        for container in manifest["containers"].values():
            self.assertNotIn(container["id"],old)
            self.assertEqual(container["state"],"exited")
            self.assertEqual(container["exit_code"],0)
            self.assertFalse(container["privileged"])
            self.assertFalse(container["published_ports"])
            self.assertLessEqual(container["memory_bytes"],4*1024**3)
            self.assertLessEqual(container["cpu_nanocpus"],2_000_000_000)
            self.assertLessEqual(container["pids_limit"],256)

    def test_every_query_and_mandatory_plan_revalidates_in_separate_measurements(self):
        for size in (30,1000,10000):
            stage=read(f"final/{size}/stage.json")
            data=corpus(size)
            fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            self.assertEqual(fingerprint,stage["corpus"]["sha256"])
            oracle=expected(data)
            for mode in ("baseline","additional_indexes"):
                self.assertEqual(set(stage[mode]),set(oracle))
                for name,query in stage[mode].items():
                    self.assertEqual(query["expected"],oracle[name])
                    for engine,measurement in query["engines"].items():
                        self.assertEqual(measurement["authentication_profile"],"postgres_native_trust" if engine=="postgresql" else "bearer_session")
                        samples=measurement["samples_ms"]
                        self.assertEqual(len(samples),15)
                        self.assertTrue(all(math.isfinite(t) and t>=0 for t in samples))
                        self.assertNotIn("EXPLAIN",measurement["sql"])
                        profiled=measurement["plan_measurement"]
                        parser=postgres_plan if engine=="postgresql" else surreal_plan
                        parsed=parser(profiled["response"],expected_rows=len(oracle[name]))
                        self.assertTrue(parsed["validated"])
                        self.assertEqual(parsed["scope"],"separate_profiled_execution")
                        self.assertNotIn("samples_ms",profiled)

    def test_utf8_batches_and_committed_receipts_reproduce_without_gaps_or_duplicates(self):
        for size in (30,1000,10000):
            data=corpus(size)
            for engine,statements in (("postgresql",pg_statements(data)),("surrealdb",surreal_load(data))):
                batches=plan(statements,max_statements=3 if size==30 else 150)
                stored=read(f"final/{size}/{engine}-batch-plan.json")["batches"]
                self.assertEqual([{k:v for k,v in b.items() if k!='request_body_bytes'} for b in stored],[b.receipt() for b in batches])
                self.assertTrue(all(0<b["request_body_bytes"]<=512*1024 for b in stored))
                journal=[json.loads(line) for line in (ROOT/f"final/{size}/{engine}-batch-receipts.jsonl").read_text().splitlines()]
                self.assertEqual(journal,stored)
                self.assertEqual(len({r["batch_id"] for r in journal}),len(batches))
        for engine in ("postgresql","surrealdb"):
            proof=read(f"final/30/{engine}-batch-ingestion.json")
            self.assertTrue(proof["interrupted_between_batches"])
            self.assertTrue(proof["next_batch_rolled_back"])
            self.assertTrue(proof["reconnected"])
            self.assertEqual(proof["resume"]["already_acknowledged"],1)
            self.assertEqual(proof["second_resume"]["applied"],0)
            self.assertTrue(proof["complete_content_stable_on_replay"])

    def test_restores_and_discovery_guarantees_have_real_evidence_and_explicit_limits(self):
        for size in (30,1000,10000):
            restored=read(f"final/{size}/restore.json")
            for engine in ("postgresql","surrealdb"):
                self.assertEqual(restored[engine]["before"],restored[engine]["restored"])
            self.assertTrue(restored["source_destinations_distinct"])
        result=read("final/result.json")
        self.assertEqual(result["status"],"VERIFIED")
        self.assertEqual(result["authentication_profiles"]["surrealdb"],"bearer_session")
        self.assertTrue(result["historical_metadata_unchanged"])
        discovery=result["discovery"]
        self.assertTrue(discovery["same_name_cross_platform_identity_preserved"])
        self.assertTrue(discovery["not_observed_never_deleted"]["verified"])
        self.assertEqual(discovery["b2_restore_new_destinations"]["records"],9)
        self.assertTrue(discovery["legacy_stale_reimport_can_replace_newer_revision"])
        self.assertFalse(discovery["cas_wrong_payload_rejected"]["legacy_emitters_guarded"])
        self.assertFalse(discovery["revision_and_retry"]["remote_revision_observed"])

    def test_monitored_limits_no_oom_or_hardware_error_in_measured_interval(self):
        resource=read("final/resource_samples.json")
        self.assertIsNone(resource["failure"])
        self.assertGreater(len(resource["samples"]),10)
        for sample in resource["samples"]:
            self.assertEqual(sample["new_kernel_hardware_or_oom_error_count"],0)
            self.assertLess(sample["campaign_bytes"],6*1024**3)
            for engine,values in sample["containers"].items():
                self.assertEqual(values["oom_kill"],0)
                self.assertLess(values["memory_current_bytes"],4*1024**3)
                self.assertLess(values["pids"],256)
                self.assertLess(values["data_bytes"],2*1024**3)


if __name__=='__main__':
    unittest.main()
