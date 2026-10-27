"""Mocked network-bound discovery collection: no real HTTP requests."""

import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from collect_discovery_snapshot import collect_online, HF_MODELS, NIM_RESOURCE


AGENTS_COMMIT = "b" * 40


def fake_source(url: str, timeout: int) -> dict:
    if "huggingface.co/api/models/" in url:
        return {"id": url.split("/api/models/", 1)[1], "gated": False}
    if "api.github.com" in url:
        return {"sha": AGENTS_COMMIT}
    if "raw.githubusercontent.com" in url:
        return {"agents": [
            {"id": "a", "project": "Agent A"},
            {"id": "b", "project": "Agent B"},
            {"id": "b", "project": "Agent B"},  # Exact duplicate upstream.
            {"id": "c", "project": "Agent C"},
        ]}
    if "api.ngc.nvidia.com" in url:
        return {"profiles": [{"profile_id": "opaque", "tested_gpu_devices": []}]}
    raise AssertionError(f"Unexpected HTTP endpoint: {url}")


class OnlineDiscoveryTests(unittest.TestCase):
    def test_bounded_source_records_from_b1_adapters(self):
        with patch("collect_discovery_snapshot.get_json", side_effect=fake_source):
            records, scope = collect_online(timeout=3, agent_limit=3)
        self.assertEqual(len(records), len(HF_MODELS) + 3 + 1)
        self.assertEqual({record.entity_type for record in records},
                         {"model_artifact", "agent_resource", "nim_microservice"})
        self.assertEqual(scope["awesome-ai-agents"]["limit"], 3)
        self.assertNotIn("commit", scope["awesome-ai-agents"])
        self.assertEqual(records[-1].source_id, NIM_RESOURCE)

    def test_nvidia_404_is_normal_but_only_affects_nim(self):
        def fetch(url, timeout):
            if "api.ngc.nvidia.com" in url:
                raise HTTPError(url, 404, "not found", {}, None)
            return fake_source(url, timeout)
        with patch("collect_discovery_snapshot.get_json", side_effect=fetch):
            records, scope = collect_online(timeout=3, agent_limit=2)
        self.assertEqual(len(records), len(HF_MODELS) + 2)
        self.assertEqual(scope["nvidia-nim-metadata"]["resource_id"], NIM_RESOURCE)

    def test_agent_limit_validation(self):
        with self.assertRaisesRegex(ValueError, "agent_limit"):
            collect_online(timeout=3, agent_limit=-1)


if __name__ == "__main__":
    unittest.main()
