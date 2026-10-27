"""Offline contract tests for the public NVIDIA NIM Metadata API v1.0.0."""

import unittest

from source_adapters import (
    GpuTarget,
    assess_nim_gpu_profile,
    normalize_nvidia_nim_metadata,
)


RESOURCE = "nim/nvidia/parakeet-1-1b-rnnt-multilingual"
HARDWARE = GpuTarget(pci_device="2571:10de", vram_per_device_gb=12, gpu_count=1)


def make_record(*profiles, **kwargs):
    return normalize_nvidia_nim_metadata(
        {"profiles": list(profiles), **kwargs}, resource_id=RESOURCE, tag="1.5.0"
    )


def make_profile(**values):
    return {"profile_id": "opaque-id-1", "tested_gpu_devices": [], **values}


class NvidiaNimContractTests(unittest.TestCase):
    def test_profiles_identity_release_and_explicit_false(self):
        record = make_record(
            make_profile(
                gpu_device="2571:10de", gpu="RTX A2000", min_vram_per_device_gb=8,
                feat_lora=False, tensor_parallel_size=1, workspace_hash="opaque-digest"
            ),
            release_details={"container_version": "1.5.0"},
            features={"tool_calling": False, "context_window": 0, "vgpu_support": True},
        )
        self.assertEqual(record.entity_type, "nim_microservice")
        self.assertEqual(record.source_id, RESOURCE)
        self.assertEqual(record.source_revision, "1.5.0")
        self.assertEqual(record.relationships, ())
        self.assertEqual(record.attributes["registry_entitlement"], "unknown")
        self.assertIs(record.attributes["tool_calling"], False)
        self.assertEqual(record.attributes["context_window"], 0)
        self.assertIs(record.attributes["vgpu_support"], True)
        self.assertIs(record.attributes["profiles"][0]["feat_lora"], False)
        self.assertEqual(record.attributes["profiles"][0]["gpu_device"], ["2571:10de"])

    def test_absent_sections_are_unknown_and_empty_tested_is_preserved(self):
        record = normalize_nvidia_nim_metadata({}, resource_id=RESOURCE, tag="1.5.0")
        self.assertIsNone(record.attributes["profiles_count"])
        self.assertIsNone(record.attributes["profiles"])
        self.assertIsNone(record.attributes["tool_calling"])
        record = make_record(make_profile())
        profile = record.attributes["profiles"][0]
        self.assertEqual(profile["tested_gpu_devices"], [])
        self.assertIsNone(profile["gpu_device"])
        self.assertIsNone(profile["min_vram_per_device_gb"])
        self.assertEqual(
            assess_nim_gpu_profile(profile, hardware=HARDWARE)["status"],
            "candidate_unverified",
        )

    def test_future_gpu_arrays_and_case_normalization(self):
        profile = make_record(make_profile(
            gpu_device=["2571:10DE", "26b9:10de"], gpu=["RTX A2000", "L40S"],
            tested_gpu_devices=["2571:10DE"], min_vram_per_device_gb=11.5,
        )).attributes["profiles"][0]
        assessment = assess_nim_gpu_profile(profile, hardware=HARDWARE)
        self.assertEqual(assessment["targeting"], "direct")
        self.assertEqual(assessment["status"], "candidate_recorded_constraints_met")
        self.assertFalse(assessment["runtime_verified"])

    def test_tested_target_is_not_direct_target(self):
        profile = make_record(make_profile(
            gpu_device="2330:10de", tested_gpu_devices=["2571:10de"],
            min_vram_per_device_gb=4,
        )).attributes["profiles"][0]
        self.assertEqual(assess_nim_gpu_profile(profile, hardware=HARDWARE)["targeting"], "tested")

    def test_other_gpu_and_vram_floor_exclude(self):
        profile = make_record(make_profile(
            gpu_device="2330:10de", min_vram_per_device_gb=80,
        )).attributes["profiles"][0]
        result = assess_nim_gpu_profile(profile, hardware=HARDWARE)
        self.assertEqual(result["status"], "excluded")
        self.assertIn("target_gpu_not_listed", result["blocking_reasons"])
        self.assertIn("insufficient_vram_per_gpu", result["blocking_reasons"])

    def test_parallelism_requires_multiple_physical_gpus(self):
        profile = make_record(make_profile(
            tensor_parallel_size=2, pipeline_parallel_size=2, min_vram_per_device_gb=8,
        )).attributes["profiles"][0]
        result = assess_nim_gpu_profile(profile, hardware=HARDWARE)
        self.assertEqual(result["required_gpus"], 4)
        self.assertIn("insufficient_gpu_count", result["blocking_reasons"])

    def test_host_driver_and_disk_constraints_not_silently_passing(self):
        profile = make_record(make_profile(
            min_vram_per_device_gb=6, min_cpu_count=24, min_driver_version="590.0",
            system_memory_per_device_gb=64, disk_space_per_device_gb=128,
        )).attributes["profiles"][0]
        result = assess_nim_gpu_profile(profile, hardware=HARDWARE)
        self.assertEqual(result["status"], "candidate_unverified")
        self.assertEqual(len(result["unverified_requirements"]), 4)

    def test_invalid_id_tag_and_type_rejected(self):
        for resource_id, tag in (("nim/nvidia/model:1.5", "1.5"), ("nim/model", "release/bad"), ("nim", "1.5")):
            with self.subTest(resource_id=resource_id, tag=tag), self.assertRaises(ValueError):
                normalize_nvidia_nim_metadata({}, resource_id=resource_id, tag=tag)
        for profile in (
            {"profile_id": "opaque"},
            make_profile(gpu_device={"unexpected": 1}),
            make_profile(tested_gpu_devices=["bad-id"]),
            make_profile(tensor_parallel_size=True),
            make_profile(min_vram_per_device_gb=-1),
            make_profile(feat_lora="false"),
        ):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                make_record(profile)

    def test_unknown_fields_pass_through_in_raw_metadata(self):
        new_metadata = {"profiles": [make_profile(future_field="new")], "future_section": {"x": 1}}
        record = normalize_nvidia_nim_metadata(new_metadata, resource_id=RESOURCE, tag="1.5.0")
        self.assertEqual(record.raw_metadata, new_metadata)
        self.assertNotIn("future_field", record.attributes["profiles"][0])


if __name__ == "__main__":
    unittest.main()
