"""Offline contract tests for external source schemas observed on 2026-10-27."""

import unittest

from source_adapters import (
    normalize_awesome_agent,
    normalize_awesome_catalog,
    normalize_huggingface_model,
)


COMMIT = "5" * 40  # fixture-only example; not an upstream commit


class HuggingFaceContractTests(unittest.TestCase):
    def test_gated_original_with_safetensors(self) -> None:
        record = normalize_huggingface_model({
            "id": "google/gemma-3-1b-it",
            "sha": "dcc83ea841ab6100d6b47a070329e1ba4cf78752",
            "gated": "manual",
            "cardData": {"license": "gemma", "base_model": "google/gemma-3-1b-pt"},
            "config": {"architectures": ["Gemma3ForCausalLM"]},
            "safetensors": {"total": 100},
            "siblings": [{"rfilename": "config.json"}, {"rfilename": "model.safetensors"}],
        })
        self.assertEqual(record.entity_type, "model_artifact")
        self.assertEqual(record.attributes["access"], "gated")
        self.assertEqual(record.attributes["approval_mode"], "manual")
        self.assertEqual(record.attributes["available_formats"], ["safetensors"])
        self.assertEqual(record.attributes["file_count"], 2)
        self.assertEqual(record.relationships, ({
            "relation": "declared_base_model", "source": "huggingface",
            "target_id": "google/gemma-3-1b-pt",
        },))

    def test_public_gguf_variant_declares_parent(self) -> None:
        record = normalize_huggingface_model({
            "id": "ggml-org/gemma-3-1b-it-GGUF",
            "sha": "f9c28bcd85737ffc5aef028638d3341d49869c27",
            "gated": False,
            "cardData": {"license": "gemma", "base_model": ["google/gemma-3-1b-it"]},
            "gguf": {"architecture": "gemma3"},
            "siblings": [{"rfilename": "gemma-3-1b-it-Q4_K_M.gguf"}],
        })
        self.assertEqual(record.attributes["access"], "public")
        self.assertIsNone(record.attributes["approval_mode"])
        self.assertIsNone(record.attributes["architectures"])
        self.assertEqual(record.attributes["available_formats"], ["gguf"])
        self.assertEqual(record.relationships[0]["target_id"], "google/gemma-3-1b-it")
        self.assertNotEqual(record.source_id, record.relationships[0]["target_id"])

    def test_unknown_is_not_public_or_empty(self) -> None:
        record = normalize_huggingface_model({"id": "example/model"})
        self.assertEqual(record.attributes["access"], "unknown")
        self.assertIsNone(record.attributes["license"])
        self.assertIsNone(record.attributes["file_count"])
        self.assertEqual(record.attributes["available_formats"], [])
        self.assertIsNone(record.attributes["base_models"])

    def test_auto_gating_and_true_gating(self) -> None:
        automatic = normalize_huggingface_model({"id": "a/auto", "gated": "auto"})
        unspecified = normalize_huggingface_model({"id": "a/yes", "gated": True})
        self.assertEqual(automatic.attributes["approval_mode"], "auto")
        self.assertEqual(unspecified.attributes["approval_mode"], "unspecified")

    def test_unexpected_schema_rejected(self) -> None:
        for bad in (0, "false", {"unexpected": 1}):
            with self.subTest(gated=bad), self.assertRaises(ValueError):
                normalize_huggingface_model({"id": "a/model", "gated": bad})
        with self.assertRaises(ValueError):
            normalize_huggingface_model({"id": "a/model", "cardData": {"base_model": [False]}})
        with self.assertRaises(ValueError):
            normalize_huggingface_model({"id": "a/model", "siblings": "not-a-list"})


class AwesomeAgentsContractTests(unittest.TestCase):
    def test_agent_resource_has_own_domain(self) -> None:
        record = normalize_awesome_agent({
            "id": "aster-712d33a8",
            "project": "Aster",
            "project_description": "Local-first agent",
            "has_public_repository": True,
            "categories": ["AI Agents"],
            "sources": [{"source": "github", "source_url": "https://github.com/Zfinix/aster", "stars": 107}],
        }, source_commit=COMMIT)
        self.assertEqual(record.entity_type, "agent_resource")
        self.assertEqual(record.source, "awesome-ai-agents")
        self.assertEqual(record.source_revision, COMMIT)
        self.assertEqual(record.attributes["source_count"], 1)
        self.assertEqual(record.attributes["source_urls"], ["https://github.com/Zfinix/aster"])
        self.assertEqual(record.relationships, ())
        self.assertEqual(record.raw_metadata["sources"][0]["stars"], 107)

    def test_multi_source_and_missing_optional_values(self) -> None:
        record = normalize_awesome_agent({
            "id": "x", "project": "X", "sources": [{"source_url": "https://example.org"}, {}],
        }, source_commit=COMMIT)
        self.assertEqual(record.attributes["source_count"], 2)
        self.assertIsNone(record.attributes["categories"])
        self.assertIsNone(record.attributes["has_public_repository"])
        self.assertEqual(record.attributes["source_urls"], ["https://example.org"])

    def test_exact_duplicates_collapse_but_conflicts_are_rejected(self) -> None:
        sample = {"id": "x", "project": "X"}
        self.assertEqual(
            len(normalize_awesome_catalog({"agents": [sample, sample]}, source_commit=COMMIT)), 1
        )
        with self.assertRaisesRegex(ValueError, "conflicting agent ID"):
            normalize_awesome_catalog(
                {"agents": [sample, {"id": "x", "project": "Different"}]}, source_commit=COMMIT,
            )

    def test_required_snapshot_revision_and_catalog_shape(self) -> None:
        sample = {"id": "x", "project": "X"}
        with self.assertRaisesRegex(ValueError, "pinned lowercase Git SHA-1"):
            normalize_awesome_agent(sample, source_commit="main")
        with self.assertRaises(ValueError):
            normalize_awesome_catalog({"agents": {}}, source_commit=COMMIT)


if __name__ == "__main__":
    unittest.main()
