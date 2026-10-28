"""Synthetic query oracles and report gates; no actual engine metrics collected."""

from copy import deepcopy
import math
import unittest
from unittest.mock import patch

from comparison_workload import comparison, load_workload, validate_measurement


class Comparison(unittest.TestCase):
    def setUp(self):
        for target in ("socket.create_connection", "socket.socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("No engine or network in reference tests"))
            guard.start()
            self.addCleanup(guard.stop)
        self.corpus, self.fingerprint = load_workload()

    def simulated_report(self, engine):
        # Deliberately simulated numbers, solely for acceptance/rejection tests.
        return {"format": "pepeuch-ai.db-comparison-measurement/v1", "engine": engine,
                "version": "synthetic-test-only", "image_digest": "sha256:" + "a" * 64,
                "corpus_sha256": self.fingerprint, "timing_scope": "persistent_client",
                "resources": {"cpu_limit": 1, "memory_limit_bytes": 1000, "peak_rss_bytes": 500, "cpu_seconds": 2},
                "indexes": [], "queries": {q: {"result": deepcopy(result), "samples_ms": list(range(1, 21)),
                                                 "plan": "synthetic-test-plan", "cache_state": "warm"}
                                            for q, result in self.corpus["expected"].items()},
                "import_update": {"verified": True, "evidence": "synthetic-test-only"},
                "backup_restore": {"verified": True, "evidence": "synthetic-test-only"}}

    def test_graph_and_relational_oracles_match_literal_references(self):
        nodes, edges, expected = self.corpus["nodes"], self.corpus["edges"], self.corpus["expected"]
        models = {m["id"]: m for m in nodes["models"]}
        variants = {v["id"]: v for v in nodes["variants"]}
        self.assertEqual(sorted(m["id"] for m in models.values() if m["provider"] == "p1"), expected["provider_models"])
        cpu = {e["from"] for e in edges if e["type"] == "supports" and e["to"] == "r1"}
        self.assertEqual(sorted(v for v in cpu if variants[v]["vram_gb"] <= 12), expected["cpu_variants"])
        gpu = {e["from"] for e in edges if e["type"] == "fits" and e["to"] == "g1"}
        runtime = {e["from"] for e in edges if e["type"] == "supports" and e["to"] == "r2"}
        self.assertEqual(sorted({variants[v]["model"] for v in gpu & runtime}), expected["typed_gpu_paths"])

    def test_exact_cosine_and_hybrid_oracles_match_independent_literal_results(self):
        models, expected = self.corpus["nodes"]["models"], self.corpus["expected"]
        def rank(hybrid):
            scored = []
            for model in models:
                vector = model["embedding"]
                cosine = vector[0] / math.sqrt(sum(x*x for x in vector))
                score = .75 * cosine + .25 * int("chat" in model["name"]) if hybrid else cosine
                scored.append({"id": model["id"], "score": round(score, 8)})
            return sorted(scored, key=lambda r: (-r["score"], r["id"]))
        self.assertEqual(rank(False), expected["vector_exact"])
        self.assertEqual(rank(True), expected["hybrid_exact"])

    def test_matched_reports_produce_percentiles_without_choosing_engine(self):
        result = comparison(self.simulated_report("postgresql"), self.simulated_report("surrealdb"))
        self.assertEqual(result["engines"]["postgresql"]["provider_models"], {"p50_ms": 10, "p95_ms": 19})
        self.assertEqual(result["decision"], "requires_review")
        self.assertEqual(result["measurement_origin"], "operator_supplied_not_attested")

    def test_launch_timings_wrong_corpus_or_incomplete_queries_rejected(self):
        for change in ({"timing_scope": "docker_exec"}, {"corpus_sha256": "0" * 64}, {"queries": {}},
                       {"image_digest": "floating-tag"}, {"engine": "unknown"}):
            report = self.simulated_report("postgresql")
            report.update(change)
            with self.assertRaises(ValueError):
                validate_measurement(report)

    def test_query_result_drift_including_false_vs_zero_rejected(self):
        for value in (False, 0.1):
            report = self.simulated_report("postgresql")
            report["queries"]["vector_exact"]["result"][-1]["score"] = value
            with self.assertRaises(ValueError):
                validate_measurement(report)

    def test_nonfinite_negative_boolean_or_missing_metrics_rejected(self):
        for value in (float("nan"), float("inf"), -1, True):
            report = self.simulated_report("postgresql")
            report["queries"]["cpu_variants"]["samples_ms"][0] = value
            with self.assertRaises(ValueError):
                validate_measurement(report)
        report = self.simulated_report("postgresql")
        report["resources"].pop("cpu_seconds")
        with self.assertRaises(ValueError):
            validate_measurement(report)

    def test_short_samples_and_unverified_restore_rejected(self):
        report = self.simulated_report("postgresql")
        report["queries"]["provider_models"]["samples_ms"] = [1]
        with self.assertRaises(ValueError):
            validate_measurement(report)
        report = self.simulated_report("postgresql")
        report["backup_restore"]["verified"] = False
        with self.assertRaises(ValueError):
            validate_measurement(report)

    def test_unmatched_limits_cache_state_or_same_engine_not_comparable(self):
        a, b = self.simulated_report("postgresql"), self.simulated_report("surrealdb")
        for kind in ("limits", "cache", "same_engine", "timing"):
            changed = deepcopy(b)
            if kind == "limits":
                changed["resources"]["cpu_limit"] = 2
            elif kind == "cache":
                changed["queries"]["provider_models"]["cache_state"] = "cold"
            elif kind == "timing":
                changed["timing_scope"] = "engine"
            else:
                changed["engine"] = "postgresql"
            with self.assertRaises(ValueError):
                comparison(a, changed)

    def test_reports_and_reference_not_mutated(self):
        a, b = self.simulated_report("postgresql"), self.simulated_report("surrealdb")
        before = deepcopy((a, b))
        comparison(a, b)
        self.assertEqual((a, b), before)
        self.assertEqual(self.corpus, load_workload()[0])


if __name__ == "__main__":
    unittest.main()
