"""No-network tests for NVIDIA read-only contract probes."""

from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

from probe_source_adapters import audit_nvidia_nim, NIM_RESOURCE, NIM_TAG


class NvidiaNimProbeTests(TestCase):
    def test_404_is_metadata_unavailable_not_missing_model(self):
        error = HTTPError("https://example.test", 404, "not found", {}, None)
        with patch("probe_source_adapters.get_json", side_effect=error):
            result = audit_nvidia_nim(2, resource_id=NIM_RESOURCE, tag=NIM_TAG)
        self.assertEqual(result["metadata_status"], "unavailable_for_tag")
        self.assertNotIn("profiles_count", result)

    def test_other_http_errors_propagate(self):
        error = HTTPError("https://example.test", 403, "forbidden", {}, None)
        with patch("probe_source_adapters.get_json", side_effect=error):
            with self.assertRaises(HTTPError):
                audit_nvidia_nim(2, resource_id=NIM_RESOURCE, tag=NIM_TAG)

    def test_public_metadata_unverified_when_vram_not_recorded(self):
        payload = {"profiles": [
            {"profile_id": "a", "gpu_device": "20b2:10de", "tested_gpu_devices": []},
            {"profile_id": "b", "tested_gpu_devices": []},
        ]}
        with patch("probe_source_adapters.get_json", return_value=payload) as fetch:
            result = audit_nvidia_nim(2, resource_id=NIM_RESOURCE, tag=NIM_TAG)
        self.assertIn("resourceId=nim%2Fnvidia%2F", fetch.call_args.args[0])
        self.assertEqual(result["profiles_count"], 2)
        self.assertEqual(result["profiles_missing_vram"], 2)
        self.assertEqual(result["screening_counts"], {"candidate_unverified": 1, "excluded": 1})
        self.assertEqual(result["targeting_counts"], {"gpu_agnostic": 1, "other_gpu": 1})
        self.assertEqual(result["registry_entitlement"], "unknown")

    def test_reject_bad_resource_before_network(self):
        with patch("probe_source_adapters.get_json") as fetch:
            with self.assertRaises(ValueError):
                audit_nvidia_nim(2, resource_id="invalid", tag="1.5.0")
        fetch.assert_not_called()
