"""B4.3 design constraints; source descriptions never collect or import SDKs."""

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import subprocess
import sys
import unittest

from source_spec_design import SOURCE_SPECS, SourceSpec, TransportSpec, source_index


ROOT = Path(__file__).resolve().parent


class SourceSpecDesignTests(unittest.TestCase):
    def test_seven_namespaces_and_resource_types_match_frozen_b33_records(self):
        reference = json.loads((ROOT / "fixtures/contracts_b40/reference.b33.json").read_text())
        self.assertEqual(set(SOURCE_SPECS), set(reference["sources"]))
        for source, item in reference["sources"].items():
            with self.subTest(source=source):
                record = item["snapshot"]["records"][0]
                spec = SOURCE_SPECS[source]
                self.assertEqual(spec.source, record["source"])
                self.assertEqual(spec.entity_types, {record["entity_type"]})
                self.assertEqual(spec.selection_modes, {item["snapshot"]["scope"][source]["mode"]})

    def test_revision_semantics_are_not_coerced_into_a_universal_commit(self):
        self.assertEqual(SOURCE_SPECS["nvidia-nim-metadata"].revision_kind, "mutable_container_tag")
        self.assertEqual(SOURCE_SPECS["moark"].revision_kind, "none")
        self.assertTrue(SOURCE_SPECS["moark"].revision_nullable)
        self.assertEqual(SOURCE_SPECS["huggingface"].revision_validation, "nonempty_string")
        for source in ("modelscope", "csghub"):
            self.assertEqual(SOURCE_SPECS[source].revision_validation, "full_hash_if_available")
            self.assertTrue(SOURCE_SPECS[source].revision_nullable)

    def test_public_metadata_does_not_advertise_working_inference_or_weights(self):
        moark = SOURCE_SPECS["moark"]
        self.assertIn("served_model_listing", moark.capabilities)
        self.assertNotIn("file_listing", moark.capabilities)
        self.assertNotIn("inference", moark.capabilities)
        self.assertEqual(SOURCE_SPECS["csghub"].entity_types, {"model_artifact"})
        self.assertNotIn("agent_resource", SOURCE_SPECS["csghub"].entity_types)
        with self.assertRaises(ValueError):
            replace(moark, capabilities={"metadata", "inference"})

    def test_sdk_and_legacy_transport_limits_do_not_claim_common_http_guarantees(self):
        sdk = SOURCE_SPECS["modelscope"]
        self.assertEqual(sdk.access_scope, "sdk_managed")
        self.assertIsNone(sdk.transport.timeout_seconds)
        self.assertIsNone(sdk.transport.max_response_bytes)
        self.assertFalse(sdk.transport.strict_url_policy)
        self.assertEqual(sdk.transport.redirects, "sdk_managed")
        for source in ("huggingface", "awesome-ai-agents", "nvidia-nim-metadata"):
            spec = SOURCE_SPECS[source]
            self.assertEqual(spec.transport.redirects, "urllib_default")
            self.assertFalse(spec.transport.strict_url_policy)
        for source in ("csghub", "moark"):
            spec = SOURCE_SPECS[source]
            self.assertTrue(spec.transport.strict_url_policy)
            self.assertEqual(spec.transport.redirects, "forbidden")

    def test_specs_index_and_nested_sets_are_not_mutable_by_callers(self):
        with self.assertRaises(TypeError):
            SOURCE_SPECS["extra"] = SOURCE_SPECS["moark"]
        with self.assertRaises(FrozenInstanceError):
            SOURCE_SPECS["moark"].source = "changed"
        with self.assertRaises(AttributeError):
            SOURCE_SPECS["moark"].entity_types.add("model_artifact")
        original = {"metadata"}
        spec = replace(SOURCE_SPECS["moark"], capabilities=original)
        original.add("file_listing")
        self.assertEqual(spec.capabilities, {"metadata"})

    def test_duplicate_and_unknown_sources_types_and_modes_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            source_index([SOURCE_SPECS["moark"], SOURCE_SPECS["moark"]])
        with self.assertRaises(KeyError):
            SOURCE_SPECS["same-name-does-not-imply-a-source"]
        for overrides in ({"entity_types": {"canonical_model"}}, {"selection_modes": {"crawl_everything"}},
                          {"revision_kind": "timestamp_is_commit"}, {"access_scope": "automatically_authorized"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                replace(SOURCE_SPECS["moark"], **overrides)

    def test_invalid_transport_claims_are_rejected(self):
        sdk = SOURCE_SPECS["modelscope"].transport
        with self.assertRaises(ValueError):
            replace(sdk, timeout_seconds=20)
        legacy = SOURCE_SPECS["huggingface"].transport
        with self.assertRaises(ValueError):
            replace(legacy, strict_url_policy=True)
        with self.assertRaises(ValueError):
            replace(SOURCE_SPECS["moark"].transport, redirects="urllib_default")
        with self.assertRaises(ValueError):
            replace(SOURCE_SPECS["models.dev"].transport, configured_hosts={"example.test"})

    def test_import_is_inert_without_optional_dependencies_adapters_or_network(self):
        # Fresh interpreter so previously loaded tests cannot hide eager imports.
        code = '''
import builtins, socket, sys
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
blocked = ('modelscope_hub', 'huggingface_hub', 'pycsghub', 'source_adapters',
           'collect_discovery_snapshot', 'probe_modelscope', 'probe_moark')
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in blocked:
        raise AssertionError('Unexpected eager dependency')
    return original(name, *args, **kwargs)
def no_network(*args, **kwargs):
    raise AssertionError('Unexpected network')
builtins.__import__ = guarded
socket.create_connection = no_network
socket.socket.connect = no_network
socket.getaddrinfo = no_network
import source_spec_design
assert len(source_spec_design.SOURCE_SPECS) == 7
assert not any(name in sys.modules for name in blocked)
print('inert source specifications')
'''
        result = subprocess.run([sys.executable, "-I", "-c", code, str(ROOT)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "inert source specifications")


if __name__ == "__main__":
    unittest.main()
